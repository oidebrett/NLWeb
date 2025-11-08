# =====================================================================
# FGAPermissionChecker
# =====================================================================
import uuid
import threading
import asyncio
import os

from openfga_sdk import OpenFgaClient, ClientConfiguration
from openfga_sdk.credentials import Credentials, CredentialConfiguration
from openfga_sdk.client.models import ClientBatchCheckItem, ClientBatchCheckRequest

from dotenv import load_dotenv
from misc.logger.logging_config_helper import get_configured_logger
from itertools import islice

logger = get_configured_logger("fga_permission_checker")

class FGAPermissionChecker:
    """
    Singleton-style FGA client manager that provides permission filtering.
    Ensures the OpenFGA client is reused across threads and event loops.
    """

    _loop = None
    _thread = None
    _client = None
    _options = None

    @classmethod
    def _ensure_background_loop(cls):
        """Ensure a persistent background asyncio event loop."""
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
        """Initialize the OpenFGA client asynchronously."""
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
        logger.info("✅ OpenFGA client initialized successfully")

    @classmethod
    def _init_client_in_loop(cls):
        """Run client creation coroutine in the background loop."""
        loop = cls._ensure_background_loop()
        future = asyncio.run_coroutine_threadsafe(cls._create_client_async(), loop)
        future.result()

    def __init__(self):
        """Ensure the FGA client is initialized once."""
        if self._client is None:
            self._init_client_in_loop()

        self.url_to_id_map = {}
        self.id_to_url_map = {}

    def url_to_doc_id(self, url: str) -> str:
        """Convert URL into a stable deterministic UUID string for FGA."""
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url))
        self.url_to_id_map[url] = doc_id
        self.id_to_url_map[doc_id] = url
        return doc_id

    def doc_id_to_url(self, doc_id: str) -> str | None:
        """Reverse lookup: find original URL from generated ID."""
        return self.id_to_url_map.get(doc_id)
    
    # -------------------
    # Core Filtering Logic
    # -------------------

    async def _filter_allowed_docs_async(self, user: str, doc_ids: list[str]) -> set[str]:
        """
        Run FGA batch checks safely (in chunks) and return the subset of doc_ids
        that the user can 'view'. Handles missing/nonexistent docs gracefully.
        """
        if not doc_ids:
            return set()

        def chunk_list(iterable, size):
            it = iter(iterable)
            while True:
                chunk = list(islice(it, size))
                if not chunk:
                    break
                yield chunk

        allowed = set()

        for batch_num, batch in enumerate(chunk_list(doc_ids, 20), start=1):
            try:
                checks = [
                    ClientBatchCheckItem(
                        user=f"user:{user}",
                        relation="viewer",
                        object=f"doc:{doc_id}" if not str(doc_id).startswith("doc:") else str(doc_id),
                    )
                    for doc_id in batch if doc_id
                ]

                if not checks:
                    continue

                body = ClientBatchCheckRequest(checks=checks)
                response = await self._client.batch_check(body, self._options)
                results = getattr(response, "result", getattr(response, "responses", []))

                for res in results:
                    if getattr(res, "allowed", False):
                        obj = getattr(res.request, "object", None)
                        if obj and obj.startswith("doc:"):
                            allowed.add(obj.split("doc:")[-1])

                logger.debug(f"✅ Processed FGA batch {batch_num} ({len(checks)} items)")
            except Exception as e:
                logger.warning(f"⚠️ FGA batch_check failed on batch {batch_num}: {e}")
                await asyncio.sleep(0.1)

        return allowed

    def filter_allowed_docs(self, user: str, doc_ids: list[str]) -> set[str]:
        """Synchronous wrapper for filtering allowed docs (runs inside background loop)."""
        loop = self._ensure_background_loop()
        future = asyncio.run_coroutine_threadsafe(self._filter_allowed_docs_async(user, doc_ids), loop)
        return future.result()

    def filter_allowed_urls(self, user: str, urls: list[str]) -> set[str]:
        """Synchronous wrapper for filtering allowed urls (runs inside background loop)."""
        # Convert URLs to doc IDs
        doc_ids = [self.url_to_doc_id(url) for url in urls]
        loop = self._ensure_background_loop()
        future = asyncio.run_coroutine_threadsafe(self._filter_allowed_docs_async(user, doc_ids), loop)
        filtered_doc_ids = future.result()
        # Convert back to URLs
        allowed_urls = [self.doc_id_to_url(doc_id) for doc_id in filtered_doc_ids if self.doc_id_to_url(doc_id)]
        return set(allowed_urls)


