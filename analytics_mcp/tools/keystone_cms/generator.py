"""Dynamic MCP Tool Generator for Keystone CMS profiles."""

from typing import Any, Callable, Dict, List, Optional
from .config import CMSProfileConfig, load_all_profiles
from .adapter import KeystoneCMSAdapter


def generate_cms_tools_for_profile(config: CMSProfileConfig) -> List[Callable[..., Any]]:
    """Generates a set of MCP tool functions for a given Keystone CMS profile."""
    adapter = KeystoneCMSAdapter(config)
    prefix = config.tool_prefix
    cms_name = config.cms_name

    tools = []

    # 1. list_recent_posts
    def list_recent_posts(limit: int = 10, state: str = "published", user_token: Optional[str] = None) -> Dict[str, Any]:
        """Lists recent posts from Keystone CMS."""
        return adapter.list_recent_posts(limit=limit, state=state, user_token=user_token)

    list_recent_posts.__name__ = f"{prefix}list_recent_posts"
    list_recent_posts.__doc__ = f"Lists recent posts from {cms_name}."
    tools.append(list_recent_posts)

    # 2. get_post
    def get_post(slug: Optional[str] = None, post_id: Optional[str] = None, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Gets a post by slug or ID with full content from Keystone CMS."""
        return adapter.get_post(slug=slug, post_id=post_id, user_token=user_token)

    get_post.__name__ = f"{prefix}get_post"
    get_post.__doc__ = f"Gets a post by slug or ID with full content from {cms_name}."
    tools.append(get_post)

    # 3. search_posts
    def search_posts(query: str, limit: int = 10, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Searches posts by title or slug query."""
        return adapter.search_posts(query=query, limit=limit, user_token=user_token)

    search_posts.__name__ = f"{prefix}search_posts"
    search_posts.__doc__ = f"Searches posts by title or slug query in {cms_name}."
    tools.append(search_posts)

    # 4. filter_posts
    def filter_posts(
        state: Optional[str] = None,
        section_id: Optional[str] = None,
        category_id: Optional[str] = None,
        tag_id: Optional[str] = None,
        writer_id: Optional[str] = None,
        limit: int = 10,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Filters posts by state, section, category, tag, or writer."""
        return adapter.filter_posts(
            state=state,
            section_id=section_id,
            category_id=category_id,
            tag_id=tag_id,
            writer_id=writer_id,
            limit=limit,
            user_token=user_token
        )

    filter_posts.__name__ = f"{prefix}filter_posts"
    filter_posts.__doc__ = f"Filters posts by state, section, category, tag, or writer in {cms_name}."
    tools.append(filter_posts)

    # 5. search_tags
    def search_tags(query: Optional[str] = None, limit: int = 20, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Searches or lists tags from Keystone CMS."""
        return adapter.search_tags(query=query, limit=limit, user_token=user_token)

    search_tags.__name__ = f"{prefix}search_tags"
    search_tags.__doc__ = f"Searches or lists tags from {cms_name}."
    tools.append(search_tags)

    # 6. convert_to_draftjs
    def convert_to_draftjs(content: str, input_type: str = "auto") -> Dict[str, Any]:
        """Converts text, Markdown, or HTML content into Keystone 6 Draft.js raw JSON format."""
        return adapter.convert_to_draftjs(content=content, input_type=input_type)

    convert_to_draftjs.__name__ = f"{prefix}convert_to_draftjs"
    convert_to_draftjs.__doc__ = f"Converts text, Markdown, or HTML into Draft.js JSON for {cms_name}."
    tools.append(convert_to_draftjs)

    # 7. create_post
    def create_post(
        title: str,
        slug: str,
        content: str,
        state: str = "draft",
        subtitle: Optional[str] = None,
        input_type: str = "auto",
        section_ids: Optional[List[str]] = None,
        category_ids: Optional[List[str]] = None,
        tag_ids: Optional[List[str]] = None,
        writer_ids: Optional[List[str]] = None,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new post in Keystone CMS."""
        return adapter.create_post(
            title=title,
            slug=slug,
            content=content,
            state=state,
            subtitle=subtitle,
            input_type=input_type,
            section_ids=section_ids,
            category_ids=category_ids,
            tag_ids=tag_ids,
            writer_ids=writer_ids,
            user_token=user_token
        )

    create_post.__name__ = f"{prefix}create_post"
    create_post.__doc__ = f"Creates a new post in {cms_name}."
    tools.append(create_post)

    # 8. update_post
    def update_post(
        post_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        state: Optional[str] = None,
        subtitle: Optional[str] = None,
        input_type: str = "auto",
        section_ids: Optional[List[str]] = None,
        category_ids: Optional[List[str]] = None,
        tag_ids: Optional[List[str]] = None,
        writer_ids: Optional[List[str]] = None,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Updates an existing post in Keystone CMS."""
        return adapter.update_post(
            post_id=post_id,
            title=title,
            content=content,
            state=state,
            subtitle=subtitle,
            input_type=input_type,
            section_ids=section_ids,
            category_ids=category_ids,
            tag_ids=tag_ids,
            writer_ids=writer_ids,
            user_token=user_token
        )

    update_post.__name__ = f"{prefix}update_post"
    update_post.__doc__ = f"Updates an existing post in {cms_name}."
    tools.append(update_post)

    # 9. publish_post
    def publish_post(post_id: str, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Publishes a post by updating state to 'published'."""
        return adapter.publish_post(post_id=post_id, user_token=user_token)

    publish_post.__name__ = f"{prefix}publish_post"
    publish_post.__doc__ = f"Publishes a post in {cms_name}."
    tools.append(publish_post)

    # 10. get_my_profile
    def get_my_profile(user_token: Optional[str] = None) -> Dict[str, Any]:
        """Gets current authenticated SSO user's CMS profile and role permissions."""
        return adapter.get_my_profile(user_token=user_token)

    get_my_profile.__name__ = f"{prefix}get_my_profile"
    get_my_profile.__doc__ = f"Gets current authenticated SSO user's CMS profile and role permissions in {cms_name}."
    tools.append(get_my_profile)

    return tools


def get_all_cms_tools() -> List[Callable[..., Any]]:
    """Loads all profiles and returns generated MCP tools."""
    profiles = load_all_profiles()
    all_tools = []
    for profile in profiles:
        tools = generate_cms_tools_for_profile(profile)
        all_tools.extend(tools)
    return all_tools
