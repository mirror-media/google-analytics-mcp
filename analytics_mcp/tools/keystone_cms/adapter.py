"""Schema-driven Keystone CMS Adapter."""

import json
from typing import Any, Dict, List, Optional
from .config import CMSProfileConfig
from .base_client import KeystoneCMSBaseClient
from .draftjs import convert_to_draftjs


class KeystoneCMSAdapter:
    """Schema-driven adapter for executing operations against a configured Keystone CMS instance."""

    def __init__(self, config: CMSProfileConfig):
        self.config = config
        self.schema = config.schema
        self.post_list = self.schema.get("post_list", "posts")
        self.tag_list = self.schema.get("tag_list", "tags")
        
        # Build post field selection query from profile config
        fields_dict = self.schema.get("fields", {})
        relations_dict = self.schema.get("relations", {})
        
        base_fields = [v for k, v in fields_dict.items() if k not in ("brief", "content", "summary")]
        relation_fields = list(relations_dict.values())
        
        self.post_base_fields = " ".join(base_fields + relation_fields)
        self.brief_field = fields_dict.get("brief", "")
        self.content_field = fields_dict.get("content", "content")
        self.summary_field = fields_dict.get("summary", "")

    def _get_client(self, user_token: Optional[str] = None) -> KeystoneCMSBaseClient:
        return KeystoneCMSBaseClient(self.config, user_token=user_token)

    def _build_post_query(self, include_rich_text: bool) -> str:
        rich_fields = []
        if include_rich_text:
            if self.brief_field:
                rich_fields.append(self.brief_field)
            if self.content_field:
                rich_fields.append(self.content_field)
            if self.summary_field:
                rich_fields.append(self.summary_field)
        
        return f"{self.post_base_fields} {' '.join(rich_fields)}"

    def list_recent_posts(self, limit: int = 10, state: str = "published", user_token: Optional[str] = None) -> Dict[str, Any]:
        """Lists recent posts from Keystone CMS."""
        client = self._get_client(user_token)
        query = f"""
        query ListPosts($take: Int!, $state: String) {{
            {self.post_list}(take: $take, where: {{ state: {{ equals: $state }} }}, orderBy: [{{ publishedDate: desc }}]) {{
                {self._build_post_query(include_rich_text=False)}
            }}
        }}
        """
        data = client.execute(query, {"take": limit, "state": state})
        return {"posts": data.get(self.post_list, [])}

    def get_post(self, slug: Optional[str] = None, post_id: Optional[str] = None, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Gets a post by slug or ID with full content from Keystone CMS."""
        if not slug and not post_id:
            raise ValueError("Either slug or post_id must be provided")

        client = self._get_client(user_token)
        if slug:
            query = f"""
            query GetPostBySlug($slug: String!) {{
                {self.post_list}(where: {{ slug: {{ equals: $slug }} }}, take: 1) {{
                    {self._build_post_query(include_rich_text=True)}
                }}
            }}
            """
            variables = {"slug": slug}
        else:
            query = f"""
            query GetPostByID($id: ID!) {{
                {self.post_list}(where: {{ id: {{ equals: $id }} }}, take: 1) {{
                    {self._build_post_query(include_rich_text=True)}
                }}
            }}
            """
            variables = {"id": post_id}

        data = client.execute(query, variables)
        posts = data.get(self.post_list, [])
        if not posts:
            return {"post": None, "message": f"Post not found ({slug or post_id})"}
        return {"post": posts[0]}

    def search_posts(self, query: str, limit: int = 10, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Searches posts by title or slug query."""
        client = self._get_client(user_token)
        gql_query = f"""
        query SearchPosts($query: String!, $take: Int!) {{
            {self.post_list}(
                where: {{ OR: [{{ title: {{ contains: $query }} }}, {{ slug: {{ contains: $query }} }}] }},
                take: $take,
                orderBy: [{{ publishedDate: desc }}]
            ) {{
                {self._build_post_query(include_rich_text=False)}
            }}
        }}
        """
        data = client.execute(gql_query, {"query": query, "take": limit})
        return {"posts": data.get(self.post_list, [])}

    def filter_posts(
        self,
        state: Optional[str] = None,
        section_id: Optional[str] = None,
        category_id: Optional[str] = None,
        tag_id: Optional[str] = None,
        writer_id: Optional[str] = None,
        limit: int = 10,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Filters posts by state, section, category, tag, or writer."""
        client = self._get_client(user_token)
        where_conditions = {}
        if state:
            where_conditions["state"] = {"equals": state}
        if section_id:
            where_conditions["sections"] = {"some": {"id": {"equals": section_id}}}
        if category_id:
            where_conditions["categories"] = {"some": {"id": {"equals": category_id}}}
        if tag_id:
            where_conditions["tags"] = {"some": {"id": {"equals": tag_id}}}
        if writer_id:
            where_conditions["writers"] = {"some": {"id": {"equals": writer_id}}}

        gql_query = f"""
        query FilterPosts($where: PostWhereInput!, $take: Int!) {{
            {self.post_list}(where: $where, take: $take, orderBy: [{{ publishedDate: desc }}]) {{
                {self._build_post_query(include_rich_text=False)}
            }}
        }}
        """
        data = client.execute(gql_query, {"where": where_conditions, "take": limit})
        return {"posts": data.get(self.post_list, [])}

    def search_tags(self, query: Optional[str] = None, limit: int = 20, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Searches or lists tags from Keystone CMS."""
        client = self._get_client(user_token)
        where_clause = "{ name: { contains: $query } }" if query else "{}"
        variables = {"query": query, "take": limit} if query else {"take": limit}

        gql_query = f"""
        query SearchTags($query: String, $take: Int!) {{
            {self.tag_list}(where: {where_clause}, take: $take) {{
                id
                name
            }}
        }}
        """
        data = client.execute(gql_query, variables)
        return {"tags": data.get(self.tag_list, [])}

    def convert_to_draftjs(
        self,
        content: str,
        input_type: str = "auto"
    ) -> Dict[str, Any]:
        """Converts text, Markdown, or HTML content into Keystone 6 Draft.js raw JSON format."""
        return convert_to_draftjs(content, input_type=input_type)

    def create_post(
        self,
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
        client = self._get_client(user_token)
        draftjs_result = convert_to_draftjs(content, input_type=input_type)
        draftjs_json = draftjs_result["draftjs_json"]

        create_data: Dict[str, Any] = {
            "title": title,
            "slug": slug,
            "state": state,
            "content": draftjs_json
        }
        if subtitle:
            create_data["subtitle"] = subtitle
        if section_ids:
            create_data["sections"] = {"connect": [{"id": sid} for sid in section_ids]}
        if category_ids:
            create_data["categories"] = {"connect": [{"id": cid} for cid in category_ids]}
        if tag_ids:
            create_data["tags"] = {"connect": [{"id": tid} for tid in tag_ids]}
        if writer_ids:
            create_data["writers"] = {"connect": [{"id": wid} for wid in writer_ids]}

        gql_query = """
        mutation CreatePost($data: PostCreateInput!) {
            createPost(data: $data) {
                id
                slug
                title
                state
            }
        }
        """
        data = client.execute(gql_query, {"data": create_data})
        return {"post": data.get("createPost")}

    def update_post(
        self,
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
        client = self._get_client(user_token)
        update_data: Dict[str, Any] = {}

        if title is not None:
            update_data["title"] = title
        if subtitle is not None:
            update_data["subtitle"] = subtitle
        if state is not None:
            update_data["state"] = state
        if content is not None:
            draftjs_result = convert_to_draftjs(content, input_type=input_type)
            update_data["content"] = draftjs_result["draftjs_json"]

        if section_ids is not None:
            update_data["sections"] = {"set": [{"id": sid} for sid in section_ids]}
        if category_ids is not None:
            update_data["categories"] = {"set": [{"id": cid} for cid in category_ids]}
        if tag_ids is not None:
            update_data["tags"] = {"set": [{"id": tid} for tid in tag_ids]}
        if writer_ids is not None:
            update_data["writers"] = {"set": [{"id": wid} for wid in writer_ids]}

        gql_query = """
        mutation UpdatePost($id: ID!, $data: PostUpdateInput!) {
            updatePost(where: { id: $id }, data: $data) {
                id
                slug
                title
                state
            }
        }
        """
        data = client.execute(gql_query, {"id": post_id, "data": update_data})
        return {"post": data.get("updatePost")}

    def publish_post(
        self,
        post_id: str,
        user_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Publishes a post by updating state to 'published'."""
        return self.update_post(post_id=post_id, state="published", user_token=user_token)

    def get_my_profile(self, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Gets current authenticated SSO user's CMS profile and role permissions."""
        from analytics_mcp.audit import current_user_email
        email = current_user_email.get() or "anonymous"
        client = self._get_client(user_token)
        user_info = client._verify_user_permission(email)
        return {"user": user_info, "cms_name": self.config.cms_name}
