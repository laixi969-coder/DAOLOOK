"""Provider endpoints are centralized and editable from the admin console.
Verified against TikHub's official App V2 guide and official SDK on 2026-09-23.
"""

ENDPOINTS = {
    "xhs_detail": {
        "path": "/api/v1/xiaohongshu/app_v2/get_image_note_detail",
        "method": "GET",
        "params": {"share_text": "{text}"},
    },
    "xhs_video": {
        "path": "/api/v1/xiaohongshu/app_v2/get_video_note_detail",
        "method": "GET",
        "params": {"share_text": "{text}"},
    },
    "xhs_profile": {
        "path": "/api/v1/xiaohongshu/app_v2/get_user_info",
        "method": "GET",
        "params": {"share_text": "{text}"},
    },
    "xhs_creator": {
        "path": "/api/v1/xiaohongshu/app_v2/get_user_posted_notes",
        "method": "GET",
        "params": {"share_text": "{text}"},
    },
    "xhs_search": {
        "path": "/api/v1/xiaohongshu/app_v2/search_notes",
        "method": "GET",
        "params": {"keyword": "{text}", "page": 1},
    },
    "douyin_detail": {
        "path": "/api/v1/douyin/app/v3/fetch_one_video_by_share_url",
        "method": "GET",
        "params": {"share_url": "{text}"},
    },
    "douyin_resolve": {
        "path": "/api/v1/douyin/web/get_sec_user_id",
        "method": "GET",
        "params": {"url": "{text}"},
    },
    "douyin_profile": {
        "path": "/api/v1/douyin/app/v3/handler_user_profile",
        "method": "GET",
        "params": {"sec_user_id": "{user_id}"},
    },
    "douyin_creator": {
        "path": "/api/v1/douyin/app/v3/fetch_user_post_videos",
        "method": "GET",
        "params": {"sec_user_id": "{user_id}", "max_cursor": 0, "count": 10},
    },
    "douyin_search": {
        "path": "/api/v1/douyin/search/fetch_video_search_v2",
        "method": "POST",
        "params": {"keyword": "{text}"},
    },
}
