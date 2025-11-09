import asyncio
import threading
import uuid
import os
from dotenv import load_dotenv
from itertools import islice
from openfga_sdk import OpenFgaClient, ClientConfiguration
from openfga_sdk.credentials import Credentials, CredentialConfiguration
from openfga_sdk.client.models import (
    ClientBatchCheckItem,
    ClientBatchCheckRequest,
    ClientListObjectsRequest,
    ClientTuple,
    ClientWriteRequest,
)
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("fga-permissions")


class FGAPermissionChecker:
    """Handles OpenFGA permission checks and site/document tuple management."""

    _loop = None
    _thread = None
    _client = None
    _options = None

    # -------------------------------------------------------------
    # Initialization helpers
    # -------------------------------------------------------------
    @classmethod
    def _ensure_background_loop(cls):
        """Ensure a persistent asyncio loop for background tasks."""
        if cls._loop is None or not cls._loop.is_running():
            cls._loop = asyncio.new_event_loop()

            def run_loop(loop):
                asyncio.set_event_loop(loop)
                loop.run_forever()

            cls._thread = threading.Thread(target=run_loop, args=(cls._loop,), daemon=True)
            cls._thread.start()

        return cls._loop

    @classmethod
    async def _create_client_async(cls):
        """Initialize FGA client asynchronously."""
        load_dotenv()

        creds = Credentials(
            method="client_credentials",
            configuration=CredentialConfiguration(
                api_issuer=os.getenv("FGA_API_TOKEN_ISSUER") or "auth.fga.dev",
                api_audience=os.getenv("FGA_API_AUDIENCE") or "https://api.us1.fga.dev/",
                client_id=os.getenv("FGA_CLIENT_ID"),
                client_secret=os.getenv("FGA_CLIENT_SECRET"),
            ),
        )

        config = ClientConfiguration(
            api_url=os.getenv("FGA_API_URL"),
            store_id=os.getenv("FGA_STORE_ID"),
            authorization_model_id=os.getenv("FGA_MODEL_ID"),
            credentials=creds,
        )

        cls._client = OpenFgaClient(config)
        cls._options = {"authorization_model_id": os.getenv("FGA_MODEL_ID")}
        logger.info("✅ FGA client initialized successfully")

    @classmethod
    def _init_client_in_loop(cls):
        """Run client creation coroutine in background loop."""
        loop = cls._ensure_background_loop()
        future = asyncio.run_coroutine_threadsafe(cls._create_client_async(), loop)
        future.result()

    def __init__(self):
        """Ensure client initialization only once."""
        if self._client is None:
            self._init_client_in_loop()

    # -------------------------------------------------------------
    # Utility functions
    # -------------------------------------------------------------
    @staticmethod
    def url_to_doc_id(url: str) -> str:
        """Convert URL to deterministic UUID-based doc ID."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, url))

    @staticmethod
    def chunk_list(iterable, size):
        """Yield successive chunks of a list."""
        it = iter(iterable)
        while True:
            chunk = list(islice(it, size))
            if not chunk:
                break
            yield chunk

    # -------------------------------------------------------------
    # Core filtering
    # -------------------------------------------------------------
    async def _filter_allowed_docs_async(self, user: str, urls: list[str]) -> set[str]:
        """Run FGA batch checks safely in chunks and return allowed URLs."""
        if not urls:
            return set()

        allowed = set()
        for batch_num, batch in enumerate(self.chunk_list(urls, 20), start=1):
            try:
                checks = [
                    ClientBatchCheckItem(
                        user=f"user:{user}",
                        relation="viewer",
                        object=f"doc:{self.url_to_doc_id(url)}",
                    )
                    for url in batch
                ]

                body = ClientBatchCheckRequest(checks=checks)
                response = await self._client.batch_check(body, self._options)
                results = getattr(response, "result", getattr(response, "responses", []))

                for i, res in enumerate(results):
                    if getattr(res, "allowed", False):
                        allowed.add(batch[i])

                logger.debug(f"✅ Processed FGA batch {batch_num} ({len(batch)} items)")
            except Exception as e:
                logger.warning(f"⚠️ FGA batch_check failed on batch {batch_num}: {e}")
                await asyncio.sleep(0.1)
        return allowed

    def filter_allowed_urls(self, user: str, urls: list[str]) -> set[str]:
        """Synchronous wrapper for FGA filtering."""
        loop = self._ensure_background_loop()
        fut = asyncio.run_coroutine_threadsafe(self._filter_allowed_docs_async(user, urls), loop)
        return fut.result()

    # -------------------------------------------------------------
    # Tuple creation (document permissions)
    # -------------------------------------------------------------
    # -------------------------------------------------------------
    # Tuple creation (document permissions) — with batching
    # -------------------------------------------------------------
    async def _add_doc_permissions_async(self, user: str, urls: list[str], site: str, relation: str = "viewer"):
        """
        Add FGA tuples linking each doc to a user and its site.
        Batches writes to stay under the API rate limit (max 20 tuples per request).
        """
        if not urls:
            return

        # Build all tuples first
        all_tuples = []
        for url in urls:
            try:
                doc_id = self.url_to_doc_id(url)
                all_tuples.append(ClientTuple(user=f"user:{user}", relation=relation, object=f"doc:{doc_id}"))
                all_tuples.append(ClientTuple(user=f"site:{site}", relation="parent_site", object=f"doc:{doc_id}"))
            except Exception as e:
                logger.warning(f"⚠️ Skipping invalid URL {url}: {e}")

        if not all_tuples:
            logger.debug("No valid tuples to add.")
            return

        # Split into batches of 20
        def chunk_list(iterable, size):
            it = iter(iterable)
            while True:
                chunk = list(islice(it, size))
                if not chunk:
                    break
                yield chunk

        total = len(all_tuples)
        success_count = 0
        batch_num = 0

        for batch in chunk_list(all_tuples, 20):
            batch_num += 1
            try:
                body = ClientWriteRequest(writes=batch)
                await self._client.write(body, self._options)
                success_count += len(batch)
                logger.info(f"✅ Batch {batch_num}: Added {len(batch)} tuples ({success_count}/{total}) for site={site}, user={user}")
            except Exception as e:
                logger.warning(f"⚠️ Batch {batch_num} failed: {e}")
                await asyncio.sleep(0.3)  # brief pause to handle rate-limiting

        logger.info(f"✅ Completed adding {success_count}/{total} tuples for site={site}, user={user}")
        return success_count

    def add_doc_permissions(self, user: str, urls: list[str], site: str):
        """Public sync wrapper for adding doc+site tuples."""
        loop = self._ensure_background_loop()
        fut = asyncio.run_coroutine_threadsafe(self._add_doc_permissions_async(user, urls, site), loop)
        return fut.result()

    # -------------------------------------------------------------
    # Site deletion (cleanup)
    # -------------------------------------------------------------
    async def _delete_site_async(self, site: str):
        """Delete all FGA tuples related to a given site."""
        try:
            response = await self._client.list_objects(
                ClientListObjectsRequest(user=f"site:{site}", relation="parent_site", type="doc"),
                self._options,
            )
            docs = getattr(response, "objects", [])
            if not docs:
                logger.info(f"No FGA docs found for site '{site}'")
                return

            deletes = [
                ClientTuple(user=f"site:{site}", relation="parent_site", object=doc)
                for doc in docs
            ]
            body = ClientWriteRequest(deletes=deletes)
            await self._client.write(body, self._options)
            logger.info(f"✅ Deleted {len(deletes)} tuples for site '{site}'")
        except Exception as e:
            logger.error(f"❌ Error deleting FGA tuples for site '{site}': {e}")

    def delete_site(self, site: str):
        """Public synchronous wrapper for deleting site tuples."""
        loop = self._ensure_background_loop()
        fut = asyncio.run_coroutine_threadsafe(self._delete_site_async(site), loop)
        return fut.result()

    # -------------------------------------------------------------
    # Site inspection / debug
    # -------------------------------------------------------------
    async def _print_site_structure_async(self, site: str):
        """Print all tuples and docs related to a site for debugging."""
        try:
            logger.info(f"🔍 Inspecting FGA structure for site '{site}'...")
            response = await self._client.list_objects(
                ClientListObjectsRequest(user=f"site:{site}", relation="parent_site", type="doc"),
                self._options,
            )
            docs = getattr(response, "objects", [])
            if not docs:
                logger.info(f"No documents linked to site '{site}'.")
                return

            logger.info(f"📄 Site '{site}' has {len(docs)} linked documents:")
            for doc in docs:
                logger.info(f"  • {doc}")

            return docs
        except Exception as e:
            logger.error(f"❌ Failed to print site structure for '{site}': {e}")
            return []

    def print_site_structure(self, site: str):
        """Public sync wrapper to print all docs under a site."""
        loop = self._ensure_background_loop()
        fut = asyncio.run_coroutine_threadsafe(self._print_site_structure_async(site), loop)
        return fut.result()
