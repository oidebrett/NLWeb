import os
import asyncio
import threading
import uuid
from itertools import islice
from dotenv import load_dotenv
from misc.logger.logging_config_helper import get_configured_logger

from openfga_sdk import ClientConfiguration, FgaObject, OpenFgaClient
from openfga_sdk.credentials import Credentials, CredentialConfiguration
from openfga_sdk.client.models import (
    ClientBatchCheckItem,
    ClientBatchCheckRequest,
    ClientWriteRequest,
    ClientTuple,
    ClientListObjectsRequest,
)
from openfga_sdk.client.models.list_users_request import ClientListUsersRequest, UserTypeFilter
import re

logger = get_configured_logger("FGAPermissionChecker")


class FGAPermissionChecker:
    _loop = None
    _thread = None
    _client = None
    _options = None

    # -------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------
    @classmethod
    def _ensure_background_loop(cls):
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
        loop = cls._ensure_background_loop()
        future = asyncio.run_coroutine_threadsafe(cls._create_client_async(), loop)
        future.result()

    def __init__(self):
        if self._client is None:
            self._init_client_in_loop()

    # -------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------
    @staticmethod
    def normalize_site_name(site: str) -> str:
        """
        Normalize site names to be FGA-safe by removing invalid characters.

        Rules:
        - Replace ':' with '_'
        - Remove trailing or leading whitespace
        - Convert to lowercase
        - Collapse any sequences of invalid characters to a single '_'
        """
        site = site.strip().lower()
        site = site.replace(":", "_")
        site = re.sub(r"[^a-z0-9._-]", "_", site)  # ensures only safe chars remain
        return site
    
    @staticmethod
    def chunk_list(iterable, size):
        it = iter(iterable)
        while True:
            chunk = list(islice(it, size))
            if not chunk:
                break
            yield chunk

    @staticmethod
    def url_to_doc_id(url: str) -> str:
        return f"doc:{uuid.uuid5(uuid.NAMESPACE_URL, url)}"

    # -------------------------------------------------------------
    # Add document + site permission tuples
    # -------------------------------------------------------------
    async def _add_doc_permissions_async(self, user: str, urls: list[str], site: str, relation: str = "viewer"):
        if not urls:
            return

        tuples = []
        for url in urls:
            try:
                obj = self.url_to_doc_id(url)
                # user → doc
                tuples.append(ClientTuple(user=f"user:{user}", relation=relation, object=obj))
                # site → doc (ownership link)
                tuples.append(ClientTuple(user=f"site:{site}", relation="parent_site", object=obj))
            except Exception as e:
                logger.warning(f"⚠️ Skipping invalid URL {url}: {e}")
                pass

        if not tuples:
            return

        unique_tuples = list({(t.user, t.relation, t.object): t for t in tuples}.values())

        for batch_num, batch in enumerate(self.chunk_list(unique_tuples, 20), start=1):
            try:
                await self._client.write(ClientWriteRequest(writes=batch), self._options)
                logger.info(f"✅ Added batch {batch_num} ({len(batch)}) tuples for user={user}, site={site}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to write FGA batch {batch_num}: {e}")
                await asyncio.sleep(0.3)

    def add_doc_permissions(self, user: str, urls: list[str], site: str, relation: str = "viewer"):
        site = self.normalize_site_name(site)
        loop = self._ensure_background_loop()
        fut = asyncio.run_coroutine_threadsafe(self._add_doc_permissions_async(user, urls, site, relation), loop)
        return fut.result()

    # -------------------------------------------------------------
    # Filter allowed URLs
    # -------------------------------------------------------------
    async def _filter_allowed_urls_async(self, user: str, urls: list[str]) -> set[str]:
        if not urls:
            return set()

        allowed = set()

        for batch_num, batch in enumerate(self.chunk_list(urls, 20), start=1):
            try:
                checks = [
                    ClientBatchCheckItem(user=f"user:{user}", relation="viewer", object=self.url_to_doc_id(url))
                    for url in batch
                ]

                body = ClientBatchCheckRequest(checks=checks)
                response = await self._client.batch_check(body, self._options)
                results = getattr(response, "result", getattr(response, "responses", []))

                for i, res in enumerate(results):
                    if getattr(res, "allowed", False):
                        allowed.add(batch[i])

                logger.debug(f"✅ Checked batch {batch_num} ({len(batch)})")
            except Exception as e:
                logger.warning(f"⚠️ FGA batch_check failed on batch {batch_num}: {e}")
                await asyncio.sleep(0.3)

        return allowed

    def filter_allowed_urls(self, user: str, urls: list[str]) -> set[str]:
        loop = self._ensure_background_loop()
        fut = asyncio.run_coroutine_threadsafe(self._filter_allowed_urls_async(user, urls), loop)
        return fut.result()

    def _extract_user_id(self, u):
        # Handle dict-based response
        if isinstance(u, dict):
            return (
                u.get("object", {}).get("id")
                or u.get("id")  # fallback if no 'object' wrapper
            )

        # Check for wildcard attribute safely
        wildcard = getattr(u, "wildcard", None)
        # Check if wildcard exists and is a user
        if wildcard is not None:
            wildcard_type = getattr(wildcard, "type", None)
            if wildcard_type is not None and wildcard_type == "user":
                return "*"

        # Handle SDK object (FgaObject or similar)
        inner_obj = getattr(u, "object", None)
        if inner_obj:
            return getattr(inner_obj, "id", None)
        
        # Final fallback
        return getattr(u, "id", None)

    # -------------------------------------------------------------
    # Delete site and all associated doc tuples
    # -------------------------------------------------------------
    async def _delete_site_async(self, site: str):
        """Optimized deletion of a site and its related document/user tuples with rate-limit handling."""
        import random

        async def safe_write_with_backoff(request, max_retries=5):
            """Write request with exponential backoff on 429s."""
            delay = 0.5
            for attempt in range(max_retries):
                try:
                    return await self._client.write(request, self._options)
                except Exception as e:
                    if e.status == 429 or "rate limit" in str(e).lower():
                        logger.warning(f"⚠️ Rate limit hit (attempt {attempt+1}), backing off {delay:.1f}s...")
                        await asyncio.sleep(delay + random.uniform(0, 0.3))
                        delay = min(delay * 2, 5.0)
                        continue
                    raise
                except Exception as e:
                    logger.warning(f"⚠️ Write failed: {e}")
                    await asyncio.sleep(delay)
            logger.error("❌ Exceeded max retries for write request")

        try:
            # 1️⃣ Get all docs linked to this site
            resp = await self._client.list_objects(
                ClientListObjectsRequest(user=f"site:{site}", relation="parent_site", type="doc"),
                self._options,
            )
            docs = getattr(resp, "objects", [])
            if not docs:
                logger.info(f"No docs found for site '{site}'")
                return

            logger.info(f"Found {len(docs)} docs for site '{site}'")

            # 2️⃣ Delete all site→doc parent_site tuples in batches
            site_doc_tuples = [ClientTuple(user=f"site:{site}", relation="parent_site", object=doc) for doc in docs]
            for batch in self.chunk_list(site_doc_tuples, 100):
                await safe_write_with_backoff(ClientWriteRequest(deletes=batch))
                await asyncio.sleep(0.2)

            # 3️⃣ Gather all user→doc viewer tuples concurrently (limited concurrency)
            sem = asyncio.Semaphore(5)

            async def fetch_users_for_doc(doc):
                async with sem:
                    try:
                        doc_id = doc.split("doc:")[-1]
                        resp = await self._client.list_users(
                            ClientListUsersRequest(
                                relation="viewer",
                                object=FgaObject(type="doc", id=doc_id),
                                user_filters=[UserTypeFilter(type="user")],
                            ),
                            self._options,
                        )
                        users = getattr(resp, "users", [])
                        return [(doc, u) for u in users]
                    except Exception as e:
                        logger.warning(f"⚠️ list_users failed for {doc}: {e}")
                        return []

            logger.info("Fetching all user→doc viewer relationships...")
            all_user_doc_pairs = []
            results = await asyncio.gather(*(fetch_users_for_doc(d) for d in docs))
            for r in results:
                all_user_doc_pairs.extend(r)

            logger.info(f"Collected {len(all_user_doc_pairs)} user→doc viewer tuples to delete")

            # 4️⃣ Delete all user→doc tuples in large batches
            delete_tuples = []
            for doc, user in all_user_doc_pairs:
                user_id = self._extract_user_id(user)
                if not user_id:
                    continue
                delete_tuples.append(ClientTuple(user=f"user:{user_id}", relation="viewer", object=doc))

            for batch in self.chunk_list(delete_tuples, 100):
                await safe_write_with_backoff(ClientWriteRequest(deletes=batch))
                await asyncio.sleep(0.2)

            logger.info(f"✅ Deleted all tuples for site '{site}' successfully")

        except Exception as e:
            logger.error(f"❌ Error deleting FGA tuples for site '{site}': {e}")


    def delete_site(self, site: str):
        site = self.normalize_site_name(site)
        loop = self._ensure_background_loop()
        fut = asyncio.run_coroutine_threadsafe(self._delete_site_async(site), loop)
        return fut.result()

    # -------------------------------------------------------------
    # Delete specific URLs (documents) for a site
    # -------------------------------------------------------------
    async def _delete_urls_async(self, site: str, urls: list[str]):
        """Delete specific document tuples for a site (site→doc and user→doc)."""

        import random

        async def safe_write_with_backoff(request, max_retries=5):
            delay = 0.5
            for attempt in range(max_retries):
                try:
                    return await self._client.write(request, self._options)
                except Exception as e:
                    if getattr(e, "status", None) == 429 or "rate limit" in str(e).lower():
                        logger.warning(f"⚠️ Rate limit hit (attempt {attempt+1}), retry in {delay:.1f}s...")
                        await asyncio.sleep(delay + random.uniform(0, 0.3))
                        delay = min(delay * 2, 5.0)
                        continue
                    raise
            logger.error("❌ Max retries exceeded for write request")

        try:
            if not urls:
                logger.info("No URLs provided for partial deletion.")
                return

            site = self.normalize_site_name(site)

            # Convert URLs → doc identifiers
            doc_ids = [f"{self.url_to_doc_id(url)}" for url in urls]

            logger.info(f"Deleting {len(doc_ids)} doc tuples for {site}...")

            # -------------------------------
            # 1️⃣ Delete site → doc tuples
            # -------------------------------
            site_doc_tuples = [
                ClientTuple(user=f"site:{site}", relation="parent_site", object=doc_id)
                for doc_id in doc_ids
            ]

            for batch in self.chunk_list(site_doc_tuples, 100):
                await safe_write_with_backoff(ClientWriteRequest(deletes=batch))
                await asyncio.sleep(0.2)

            logger.info(f"Removed {len(doc_ids)} site→doc tuples.")

            # -------------------------------
            # 2️⃣ Fetch and remove user→doc viewer tuples
            # -------------------------------

            sem = asyncio.Semaphore(5)

            async def fetch_users_for_doc(doc):
                async with sem:
                    try:
                        doc_hash = doc.replace("doc:", "")
                        resp = await self._client.list_users(
                            ClientListUsersRequest(
                                relation="viewer",
                                object=FgaObject(type="doc", id=doc_hash),
                                user_filters=[UserTypeFilter(type="user")],
                            ),
                            self._options,
                        )
                        users = getattr(resp, "users", [])
                        return [(doc, user) for user in users]
                    except Exception as e:
                        logger.warning(f"⚠️ list_users failed for {doc}: {e}")
                        return []

            logger.info("Fetching viewer tuples for removed docs...")

            user_pairs_nested = await asyncio.gather(*(fetch_users_for_doc(doc) for doc in doc_ids))
            all_user_doc_pairs = [pair for sub in user_pairs_nested for pair in sub]

            logger.info(f"Found {len(all_user_doc_pairs)} viewer tuples to delete.")

            delete_user_tuples = []
            for doc, user in all_user_doc_pairs:
                uid = self._extract_user_id(user)
                if uid:
                    delete_user_tuples.append(ClientTuple(user=f"user:{uid}", relation="viewer", object=doc))

            for batch in self.chunk_list(delete_user_tuples, 100):
                await safe_write_with_backoff(ClientWriteRequest(deletes=batch))
                await asyncio.sleep(0.2)

            logger.info(f"✅ Finished partial cleanup: {len(urls)} URLs removed for site '{site}'")

        except Exception as e:
            logger.error(f"❌ Error deleting tuples for URLs on site '{site}': {e}")

    def delete_urls(self, site: str, urls: list[str]):
        site = self.normalize_site_name(site)
        loop = self._ensure_background_loop()
        fut = asyncio.run_coroutine_threadsafe(self._delete_urls_async(site, urls), loop)
        return fut.result()

if __name__ == "__main__":
    
    checker = FGAPermissionChecker()

    print("Installing FGA CLI")
    print("sudo apt install ./fga_VERSION_linux_386.deb")
    print("fga --version")
    print("export FGA_STORE_ID=<STORE_ID>")
    print("export FGA_CLIENT_ID=<CLIENT_ID>")
    print("export FGA_CLIENT_SECRET=<CLIENT_SECRET>")
    print("export FGA_API_URL=https://api.eu1.fga.dev")
    print("export FGA_API_AUDIENCE=https://api.eu1.fga.dev/")
    print("export FGA_API_TOKEN_ISSUER='auth.fga.dev'")
    print("fga model get")
    print("fga tuple read --store-id=$FGA_STORE_ID --output-format=simple-json --max-pages=0 > tuples.json")
    print("fga tuple delete --store-id=$FGA_STORE_ID --file=tuples.json")

