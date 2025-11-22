# core/methods/NLWebFgaHandler.py
# Licensed under the MIT License.

"""
NLWebFgaHandler
---------------
A subclass of NLWebHandler that automatically filters
retrieved items using OpenFGA permissions before they are used
by higher-level handlers (e.g. GenerateAnswer).
"""
from core.retriever import search
import asyncio
from misc.logger.logging_config_helper import get_configured_logger
from core.baseHandler import NLWebHandler
import methods.fastTrackFga as fastTrackFga
from methods.fastTrackFga import site_supports_standard_retrieval
from methods.FGAPermissionChecker import FGAPermissionChecker
import core.post_ranking as post_ranking
import core.router as router
import core.query_analysis.query_rewrite as query_rewrite
from core.utils.utils import get_param, siteToItemType, log
from core.config import CONFIG


logger = get_configured_logger("nlweb_fga_handler")



# =====================================================================
# NLWebFgaHandler
# =====================================================================

class NLWebFgaHandler(NLWebHandler):
    """
    Adds OpenFGA permission filtering after retrieval.
    Subclasses (like GenerateAnswer) can inherit this safely.
    """

    def __init__(self, query_params, handler):
        super().__init__(query_params, handler)
        self.fga_checker = FGAPermissionChecker()
        self.user = self._extract_user_from_headers()

    def _extract_user_from_headers(self) -> str:
        """
        Determine the authenticated user in priority order:
        1. self.oauth_id (preferred, set by NLWebHandler auth)
        2. 'X-Forwarded-User' header
        3. query params (user or X-Forwarded-User)
        4. fallback: 'anonymous'
        """
        try:
            # 1️⃣ Prefer authenticated user from NLWebHandler
            if hasattr(self, "oauth_id") and self.oauth_id:
                return self.oauth_id

            # 2️⃣ Try proxy-injected header
            if hasattr(self, "headers") and isinstance(self.headers, dict):
                forwarded_user = self.headers.get("X-Forwarded-User")
                if forwarded_user:
                    return forwarded_user

            # 3️⃣ Fallback to query params (e.g. ?user= or ?X-Forwarded-User=)
            if isinstance(self.query_params, dict):
                qp_user = self.query_params.get("user") or self.query_params.get("X-Forwarded-User")
                if qp_user:
                    return qp_user

        except Exception as e:
            logger.warning(f"⚠️ Could not extract user from request context: {e}")

        # 4️⃣ Default fallback
        return "anonymous"

    async def prepare(self):
        tasks = []

        tasks.append(asyncio.create_task(self.decontextualizeQuery().do()))
        tasks.append(asyncio.create_task(fastTrackFga.FastTrackFGA(self).do()))
        tasks.append(asyncio.create_task(query_rewrite.QueryRewrite(self).do()))
        
        # Check if a specific tool is requested via the 'tool' parameter
        requested_tool = get_param(self.query_params, "tool", str, None)
        if requested_tool:
            # Skip tool selection and use the requested tool directly
            # Set tool_routing_results to use the specified tool
            self.tool_routing_results = [{
                "tool": type('Tool', (), {'name': requested_tool, 'handler_class': None})(),
                "score": 100,
                "result": {"score": 100, "justification": f"Tool {requested_tool} specified in request"}
            }]
        else:
            # Normal tool selection
            tasks.append(asyncio.create_task(router.ToolSelector(self).do()))

        try:
            if CONFIG.should_raise_exceptions():
                # In testing/development mode, raise exceptions to fail tests properly
                await asyncio.gather(*tasks)
            else:
                # In production mode, catch exceptions to avoid crashing
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            if CONFIG.should_raise_exceptions():
                raise  # Re-raise in testing/development mode
        finally:
            self.pre_checks_done_event.set()  # Signal completion regardless of errors
            self.state.set_pre_checks_done()
         
        # Wait for retrieval to be done
        if not self.retrieval_done_event.is_set():
            # Skip retrieval for sites without embeddings
            if not site_supports_standard_retrieval(self.site):
                self.final_retrieved_items = []
                self.retrieval_done_event.set()
            else:
                items = await search(
                    self.decontextualized_query, 
                    self.site,
                    query_params=self.query_params,
                    handler=self
                )
                self.final_retrieved_items = items
                self.retrieval_done_event.set()
        if not hasattr(self, "final_retrieved_items") or not self.final_retrieved_items:
            logger.debug("No retrieved items to filter.")
            return

        logger.info(f"🔒 Applying FGA filtering for user: {self.user}")

        # The item structure is (url, schema_json, name, site)
        urls = [url for (url, *_rest) in self.final_retrieved_items]

        try:
            allowed = self.fga_checker.filter_allowed_urls(self.user, urls)
        except Exception as e:
            logger.error(f"FGA filtering failed: {e}")
            allowed = set()

        before = len(self.final_retrieved_items)
        self.final_retrieved_items = [item for item in self.final_retrieved_items if item[0] in allowed]
        after = len(self.final_retrieved_items)
        logger.info(f"✅ Filtered {before} → {after} items after FGA permission check.")
        
        logger.info("Preparation phase completed")

'''
    async def prepare(self):
        """
        Runs NLWebHandler.prepare() first, then applies FGA filtering.
        """
        logger.info("🔍 NLWebFgaHandler: Running base prepare()")
        await super().prepare()

        if not hasattr(self, "final_retrieved_items") or not self.final_retrieved_items:
            logger.debug("No retrieved items to filter.")
            return

        logger.info(f"🔒 Applying FGA filtering for user: {self.user}")

        # The item structure is (url, schema_json, name, site)
        doc_ids = [url for (url, *_rest) in self.final_retrieved_items]

        try:
            allowed = self.fga_checker.filter_allowed_docs(self.user, doc_ids)
        except Exception as e:
            logger.error(f"FGA filtering failed: {e}")
            allowed = set()

        before = len(self.final_retrieved_items)
        self.final_retrieved_items = [item for item in self.final_retrieved_items if item[0] in allowed]
        after = len(self.final_retrieved_items)
        logger.info(f"✅ Filtered {before} → {after} items after FGA permission check.")
'''