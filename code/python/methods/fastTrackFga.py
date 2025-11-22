# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
FastTrackFGA: A variant of the FastTrack pipeline that adds OpenFGA-based
permission filtering before ranking. This ensures that only items the current
user is allowed to 'view' are passed on for ranking.
"""

from core.retriever import search
import core.ranking as ranking
from misc.logger.logging_config_helper import get_configured_logger
from methods.FGAPermissionChecker import FGAPermissionChecker

logger = get_configured_logger("fast_track_fga")

NO_STANDARD_RETRIEVAL_SITES = [
    "datacommons", "all", "conv_history", "CricketLens", "cricketlens", "cricketlens.com"
]


def site_supports_standard_retrieval(site):
    """Check if a site supports standard vector database retrieval"""
    return site not in NO_STANDARD_RETRIEVAL_SITES

class FastTrackFGA:
    """FastTrack variant that filters retrieved docs using OpenFGA permissions."""

    def __init__(self, handler):
        self.handler = handler
        self.permission_checker = FGAPermissionChecker()
        logger.debug("FastTrackFGA initialized")

    def is_fastTrack_eligible(self):
        """Check if query is eligible for fast track processing"""
        if not site_supports_standard_retrieval(self.handler.site):
            return False
        if self.handler.context_url:
            return False
        if len(self.handler.prev_queries) > 0:
            return False
        return True

    async def do(self):
        """Execute fast track with OpenFGA permission filtering."""
        if not self.is_fastTrack_eligible():
            logger.info("Fast track skipped — not eligible")
            return

        self.handler.retrieval_done_event.set()
        try:
            logger.info("Starting FastTrackFGA search")
            items = await search(
                self.handler.query,
                self.handler.site,
                query_params=self.handler.query_params,
                handler=self.handler,
            )

            logger.info(f"Retrieved {len(items)} items before FGA filtering")

            # Extract URLs to use as doc IDs for FGA
            urls = [item[0] for item in items if item and item[0]]

            # Determine current user (prefer self.oauth_id)
            user = getattr(self.handler, "oauth_id", None)
            if not user:
                user = getattr(self.handler, "request_user", None)

            allowed_urls = self.permission_checker.filter_allowed_urls(user, urls)
            logger.info(f"Allowed {len(allowed_urls)} / {len(urls)} items after FGA check")

            # Filter items based on allowed URLs
            filtered_items = [item for item in items if item[0] in allowed_urls]
            self.handler.final_retrieved_items = filtered_items

            # Continue to ranking if query still active
            if not self.handler.query_done and not self.handler.abort_fast_track_event.is_set():
                self.handler.fastTrackRanker = ranking.Ranking(
                    self.handler, filtered_items, ranking.Ranking.FAST_TRACK
                )
                await self.handler.fastTrackRanker.do()
        except Exception as e:
            logger.error(f"Error during FastTrackFGA: {e}")
            raise
