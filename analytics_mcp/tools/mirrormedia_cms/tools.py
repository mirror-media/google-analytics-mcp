"""Mirror Media CMS MCP Tools."""

import json
from typing import Any, Dict, List, Optional
from analytics_mcp.tools.mirrormedia_cms.client import MirrorMediaCMSClient
from analytics_mcp.tools.mirrormedia_cms.draftjs import convert_to_draftjs, create_atomic_draftjs_entity

POST_SUMMARY_QUERY = """
query GetRecentPosts($take: Int) {
  posts(take: $take, orderBy: [{ publishedDate: desc }]) {
    id
    slug
    title
    subtitle
    state
    publishedDate
    sections { id name }
    categories { id name }
    writers { id name }
  }
}
"""

POST_DETAIL_QUERY = """
query GetPostDetail($where: PostWhereUniqueInput!) {
  post(where: $where) {
    id
    slug
    title
    subtitle
    state
    publishedDate
    style
    isMember
    isFeatured
    isAdvertised
    sections { id name }
    categories { id name }
    writers { id name }
    photographers { id name }
    camera_man { id name }
    designers { id name }
    engineers { id name }
    vocals { id name }
    tags { id name }
    heroImage { id name }
    brief
    content
    createdAt
    updatedAt
  }
}
"""

SEARCH_POSTS_QUERY = """
query SearchPosts($query: String!, $take: Int) {
  posts(
    take: $take
    orderBy: [{ publishedDate: desc }]
    where: {
      OR: [
        { title: { contains: $query } }
        { subtitle: { contains: $query } }
        { slug: { contains: $query } }
      ]
    }
  ) {
    id
    slug
    title
    subtitle
    state
    publishedDate
    sections { id name }
    categories { id name }
    writers { id name }
  }
}
"""

FILTER_POSTS_QUERY = """
query FilterPosts($where: PostWhereInput!, $take: Int) {
  posts(take: $take, orderBy: [{ publishedDate: desc }], where: $where) {
    id
    slug
    title
    subtitle
    state
    publishedDate
    sections { id name }
    categories { id name }
    writers { id name }
  }
}
"""

SEARCH_TAGS_QUERY = """
query SearchTags($query: String, $take: Int) {
  tags(
    take: $take
    orderBy: [{ name: asc }]
    where: { name: { contains: $query } }
  ) {
    id
    name
  }
}
"""

CREATE_POST_MUTATION = """
mutation CreatePost($data: PostCreateInput!) {
  createPost(data: $data) {
    id
    slug
    title
    state
    publishedDate
    createdAt
  }
}
"""

UPDATE_POST_MUTATION = """
mutation UpdatePost($where: PostWhereUniqueInput!, $data: PostUpdateInput!) {
  updatePost(where: $where, data: $data) {
    id
    slug
    title
    state
    updatedAt
  }
}
"""

CREATE_IMAGE_MUTATION = """
mutation CreateImage($data: ImageCreateInput!) {
  createImage(data: $data) {
    id
    name
    imageFile {
      url
      width
      height
    }
  }
}
"""


def mm_list_recent_posts(limit: int = 20, user_token: Optional[str] = None) -> Dict[str, Any]:
    """List recent Mirror Media CMS posts that the user is authorized to view.
    
    Args:
        limit: Number of posts to retrieve (1-100, default 20).
        user_token: Optional OAuth/CMS token for user authorization.
    """
    client = MirrorMediaCMSClient(user_token=user_token)
    take = max(1, min(100, limit))
    data = client.execute(POST_SUMMARY_QUERY, {"take": take})
    return {"posts": data.get("posts", [])}


def mm_get_post(id: Optional[str] = None, slug: Optional[str] = None, user_token: Optional[str] = None) -> Dict[str, Any]:
    """Get complete Mirror Media article details by post ID or slug.
    
    Args:
        id: Keystone Post ID.
        slug: Post URL slug.
        user_token: Optional OAuth/CMS token for user authorization.
    """
    if not id and not slug:
        raise ValueError("Must provide either 'id' or 'slug'")

    client = MirrorMediaCMSClient(user_token=user_token)
    where = {"id": id} if id else {"slug": slug}
    data = client.execute(POST_DETAIL_QUERY, {"where": where})
    return {"post": data.get("post")}


def mm_search_posts(query: str, limit: int = 20, user_token: Optional[str] = None) -> Dict[str, Any]:
    """Search Mirror Media post titles, subtitles, and slugs.
    
    Args:
        query: Search term for title/subtitle/slug.
        limit: Number of results (1-100, default 20).
        user_token: Optional OAuth/CMS token for user authorization.
    """
    if not query or not query.strip():
        raise ValueError("query term cannot be empty")

    client = MirrorMediaCMSClient(user_token=user_token)
    take = max(1, min(100, limit))
    data = client.execute(SEARCH_POSTS_QUERY, {"query": query.strip(), "take": take})
    return {"posts": data.get("posts", [])}


def mm_filter_posts(
    section_id: Optional[str] = None,
    category_id: Optional[str] = None,
    writer_id: Optional[str] = None,
    state: Optional[str] = None,
    style: Optional[str] = None,
    limit: int = 20,
    user_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Filter Mirror Media posts by section, category, writer, state, or style.
    
    Args:
        section_id: Section ID filter.
        category_id: Category ID filter.
        writer_id: Author / Writer ID filter.
        state: Post state filter (e.g. 'published', 'draft', 'scheduled').
        style: Post style filter.
        limit: Number of results (1-100, default 20).
        user_token: Optional OAuth/CMS token for user authorization.
    """
    conditions: List[Dict[str, Any]] = []
    if section_id:
        conditions.append({"sections": {"some": {"id": {"equals": section_id}}}})
    if category_id:
        conditions.append({"categories": {"some": {"id": {"equals": category_id}}}})
    if writer_id:
        conditions.append({"writers": {"some": {"id": {"equals": writer_id}}}})
    if state:
        conditions.append({"state": {"equals": state}})
    if style:
        conditions.append({"style": {"equals": style}})

    if not conditions:
        raise ValueError("At least one filter condition must be supplied")

    where = {"AND": conditions}
    client = MirrorMediaCMSClient(user_token=user_token)
    take = max(1, min(100, limit))
    data = client.execute(FILTER_POSTS_QUERY, {"where": where, "take": take})
    return {"posts": data.get("posts", [])}


def mm_search_tags(query: Optional[str] = None, limit: int = 20, user_token: Optional[str] = None) -> Dict[str, Any]:
    """Search active Mirror Media tags.
    
    Args:
        query: Tag name fragment.
        limit: Maximum results (1-100, default 20).
        user_token: Optional OAuth/CMS token for user authorization.
    """
    client = MirrorMediaCMSClient(user_token=user_token)
    take = max(1, min(100, limit))
    data = client.execute(SEARCH_TAGS_QUERY, {"query": query or "", "take": take})
    return {"tags": data.get("tags", [])}


def mm_convert_to_draftjs(source: str, format: str = "html") -> Dict[str, Any]:
    """Convert Google Docs HTML, Markdown, or plain text into Draft.js Raw Content State JSON for Post content/brief fields.
    
    Args:
        source: Rich text or HTML source.
        format: Format ('html', 'markdown', or 'plain_text').
    """
    if not source or not source.strip():
        raise ValueError("source string is required")
    fmt = format.lower()
    if fmt not in ("html", "markdown", "plain_text"):
        raise ValueError("format must be 'html', 'markdown', or 'plain_text'")
    return convert_to_draftjs(source, fmt)


def mm_create_post(
    title: str,
    slug: Optional[str] = None,
    subtitle: Optional[str] = None,
    state: str = "draft",
    brief: Optional[str] = None,
    content: Optional[str] = None,
    user_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new Mirror Media post (enforces user CMS role permissions).
    
    Args:
        title: Article title (required).
        slug: Article URL slug.
        subtitle: Subtitle.
        state: State (default 'draft').
        brief: Short summary or Draft.js JSON.
        content: Main body content or Draft.js JSON.
        user_token: OAuth/CMS session token enforcing user's CMS role.
    """
    if not title or not title.strip():
        raise ValueError("title is required to create a Mirror Media post")

    post_data: Dict[str, Any] = {
        "title": title.strip(),
        "state": state,
    }
    if slug:
        post_data["slug"] = slug.strip()
    if subtitle:
        post_data["subtitle"] = subtitle.strip()
    if brief:
        post_data["brief"] = brief if brief.startswith("{") else json.dumps(convert_to_draftjs(brief, "html"))
    if content:
        post_data["content"] = content if content.startswith("{") else json.dumps(convert_to_draftjs(content, "html"))

    client = MirrorMediaCMSClient(user_token=user_token)
    data = client.execute(CREATE_POST_MUTATION, {"data": post_data})
    return {"post": data.get("createPost")}


def mm_update_post(
    id: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    state: Optional[str] = None,
    brief: Optional[str] = None,
    content: Optional[str] = None,
    user_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing Mirror Media post (enforces user CMS role permissions).
    
    Args:
        id: Post ID to update (required).
        title: Updated title.
        subtitle: Updated subtitle.
        state: Updated state (e.g., 'draft', 'published').
        brief: Updated brief.
        content: Updated main content.
        user_token: OAuth/CMS session token enforcing user's CMS role.
    """
    if not id:
        raise ValueError("Post id is required for update")

    update_data: Dict[str, Any] = {}
    if title:
        update_data["title"] = title.strip()
    if subtitle:
        update_data["subtitle"] = subtitle.strip()
    if state:
        update_data["state"] = state
    if brief:
        update_data["brief"] = brief if brief.startswith("{") else json.dumps(convert_to_draftjs(brief, "html"))
    if content:
        update_data["content"] = content if content.startswith("{") else json.dumps(convert_to_draftjs(content, "html"))

    if not update_data:
        raise ValueError("At least one field to update must be provided")

    client = MirrorMediaCMSClient(user_token=user_token)
    data = client.execute(UPDATE_POST_MUTATION, {"where": {"id": id}, "data": update_data})
    return {"post": data.get("updatePost")}


def mm_publish_post(id: str, published_date: Optional[str] = None, user_token: Optional[str] = None) -> Dict[str, Any]:
    """Publish an existing draft Mirror Media post (enforces user CMS Editor/Admin role).
    
    Args:
        id: Post ID to publish.
        published_date: ISO timestamp for publish time.
        user_token: OAuth/CMS token enforcing user's CMS role.
    """
    if not id:
        raise ValueError("Post id is required")

    update_data: Dict[str, Any] = {"state": "published"}
    if published_date:
        update_data["publishedDate"] = published_date

    client = MirrorMediaCMSClient(user_token=user_token)
    data = client.execute(UPDATE_POST_MUTATION, {"where": {"id": id}, "data": update_data})
    return {"post": data.get("updatePost")}
