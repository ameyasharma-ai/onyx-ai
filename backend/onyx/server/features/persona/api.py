from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi import Response
from fastapi import UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic import model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.auth.users import current_chat_accessible_user
from onyx.auth.users import current_curator_or_admin_user
from onyx.auth.users import current_limited_user
from onyx.configs.app_configs import DISABLE_VECTOR_DB
from onyx.configs.constants import FileOrigin
from onyx.configs.constants import MilestoneRecordType
from onyx.configs.constants import PUBLIC_API_TAGS
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.enums import PersonaSharePermission
from onyx.db.file_record import get_filerecord_by_file_id_optional
from onyx.db.models import Persona
from onyx.db.models import User
from onyx.db.persona import create_assistant_label
from onyx.db.persona import create_update_persona
from onyx.db.persona import delete_persona_label
from onyx.db.persona import get_assistant_labels
from onyx.db.persona import get_minimal_persona_snapshots_for_user
from onyx.db.persona import get_minimal_persona_snapshots_paginated
from onyx.db.persona import get_persona_by_id
from onyx.db.persona import get_persona_count_for_user
from onyx.db.persona import get_persona_snapshots_for_user
from onyx.db.persona import get_persona_snapshots_paginated
from onyx.db.persona import mark_persona_as_deleted
from onyx.db.persona import mark_persona_as_not_deleted
from onyx.db.persona import remove_user_from_persona_shares
from onyx.db.persona import update_persona_featured
from onyx.db.persona import update_persona_label
from onyx.db.persona import update_persona_public_status
from onyx.db.persona import update_persona_shared
from onyx.db.persona import update_persona_visibility
from onyx.db.persona import update_personas_display_priority
from onyx.db.persona_sharing import get_persona_access_level
from onyx.db.persona_sharing import get_user_group_ids_for_user
from onyx.db.persona_sharing import persona_ownership_is_vacant
from onyx.db.users import get_active_admin_count
from onyx.db.persona import get_explore_personas_paginated
from onyx.db.persona import toggle_persona_favorite
from onyx.db.persona import rate_persona
from typing import Any
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.file_store.models import ChatFileType
from onyx.server.documents.models import PaginatedReturn
from onyx.server.features.persona.constants import ADMIN_AGENTS_RESOURCE
from onyx.server.features.persona.constants import AGENTS_RESOURCE
from onyx.server.features.persona.models import FullPersonaSnapshot
from onyx.server.features.persona.models import MinimalPersonaSnapshot
from onyx.server.features.persona.models import PersonaLabelCreate
from onyx.server.features.persona.models import PersonaLabelResponse
from onyx.server.features.persona.models import PersonaSnapshot
from onyx.server.features.persona.models import PersonaUpsertRequest
from onyx.server.features.persona.models import PersonaAutoGenerateRequest
from onyx.server.features.persona.models import PersonaAutoGenerateResponse
from onyx.llm.factory import get_default_llm
from onyx.llm.models import UserMessage, SystemMessage
from onyx.server.manage.llm.api import get_valid_model_configuration_ids_for_persona
from onyx.server.models import DisplayPriorityRequest
from onyx.server.settings.store import load_settings
from onyx.utils.logger import setup_logger
from onyx.utils.telemetry import mt_cloud_telemetry
from onyx.utils.variable_functionality import fetch_versioned_implementation
import json
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()


def _validate_user_knowledge_enabled(
    persona_upsert_request: PersonaUpsertRequest, action: str
) -> None:
    """Check if user knowledge is enabled when user files/projects are provided."""
    settings = load_settings()
    if not settings.user_knowledge_enabled:
        # Only user files are supported going forward; keep getattr for backward compat
        if persona_upsert_request.user_file_ids or getattr(
            persona_upsert_request, "user_project_ids", None
        ):
            raise HTTPException(
                status_code=400,
                detail=f"User Knowledge is disabled. Cannot {action} assistant with user files or projects.",
            )


def _validate_vector_db_knowledge(
    persona_upsert_request: PersonaUpsertRequest,
) -> None:
    """Reject connector-sourced knowledge types when vector DB is disabled.

    document_sets, hierarchy_nodes, and attached_documents all depend on
    the vector DB for search filtering. user_files are still allowed because
    they use the FileReaderTool path instead.
    """
    if not DISABLE_VECTOR_DB:
        return

    if persona_upsert_request.document_set_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot attach document sets to an assistant when the vector database is disabled (DISABLE_VECTOR_DB is set)."
            ),
        )
    if persona_upsert_request.hierarchy_node_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot attach hierarchy nodes to an assistant when the vector database is disabled (DISABLE_VECTOR_DB is set)."
            ),
        )
    if persona_upsert_request.document_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot attach documents to an assistant when the vector database is disabled (DISABLE_VECTOR_DB is set)."
            ),
        )


admin_router = APIRouter(prefix="/admin/persona")
basic_router = APIRouter(prefix="/persona")

# NOTE: Users know this functionality as "agents", so we want to start moving
# nomenclature of these REST resources to match that.
admin_agents_router = APIRouter(prefix=ADMIN_AGENTS_RESOURCE)
agents_router = APIRouter(prefix=AGENTS_RESOURCE)


class IsListedRequest(BaseModel):
    is_listed: bool


class IsPublicRequest(BaseModel):
    is_public: bool


class IsFeaturedRequest(BaseModel):
    is_featured: bool


@admin_router.patch("/{persona_id}/listed")
def patch_persona_visibility(
    persona_id: int,
    is_listed_request: IsListedRequest,
    user: User = Depends(current_curator_or_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    update_persona_visibility(
        persona_id=persona_id,
        is_listed=is_listed_request.is_listed,
        db_session=db_session,
        user=user,
    )


@basic_router.patch("/{persona_id}/public")
def patch_user_persona_public_status(
    persona_id: int,
    is_public_request: IsPublicRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        update_persona_public_status(
            persona_id=persona_id,
            is_public=is_public_request.is_public,
            db_session=db_session,
            user=user,
        )
    except ValueError as e:
        logger.exception("Failed to update persona public status")
        raise HTTPException(status_code=403, detail=str(e))


@admin_router.patch("/{persona_id}/featured")
def patch_persona_featured_status(
    persona_id: int,
    is_featured_request: IsFeaturedRequest,
    user: User = Depends(current_curator_or_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        update_persona_featured(
            persona_id=persona_id,
            is_featured=is_featured_request.is_featured,
            db_session=db_session,
            user=user,
        )
    except ValueError as e:
        logger.exception("Failed to update persona featured status")
        raise HTTPException(status_code=403, detail=str(e))


@admin_agents_router.patch("/display-priorities")
def patch_agents_display_priorities(
    display_priority_request: DisplayPriorityRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        update_personas_display_priority(
            display_priority_map=display_priority_request.display_priority_map,
            db_session=db_session,
            user=user,
            commit_db_txn=True,
        )
    except ValueError as e:
        logger.exception("Failed to update agent display priorities.")
        raise HTTPException(status_code=403, detail=str(e))


@admin_router.get("", tags=PUBLIC_API_TAGS)
def list_personas_admin(
    user: User = Depends(current_curator_or_admin_user),
    db_session: Session = Depends(get_session),
    include_deleted: bool = False,
    get_editable: bool = Query(False, description="If true, return editable personas"),
) -> list[PersonaSnapshot]:
    return get_persona_snapshots_for_user(
        user=user,
        db_session=db_session,
        get_editable=get_editable,
        include_deleted=include_deleted,
    )


@admin_agents_router.get("", tags=PUBLIC_API_TAGS)
def get_agents_admin_paginated(
    page_num: int = Query(0, ge=0, description="Page number (0-indexed)."),
    page_size: int = Query(10, ge=1, le=1000, description="Items per page."),
    user: User = Depends(current_curator_or_admin_user),
    db_session: Session = Depends(get_session),
    include_deleted: bool = Query(
        False, description="If true, includes deleted personas."
    ),
    get_editable: bool = Query(
        False, description="If true, only returns editable personas."
    ),
    include_default: bool = Query(
        True, description="If true, includes builtin/default personas."
    ),
) -> PaginatedReturn[PersonaSnapshot]:
    """Paginated endpoint for listing agents (formerly personas) (admin view).

    Returns items for the requested page plus total count.
    Agents are ordered by display_priority (ASC, nulls last) then by ID (ASC).
    """
    agents = get_persona_snapshots_paginated(
        user=user,
        db_session=db_session,
        page_num=page_num,
        page_size=page_size,
        get_editable=get_editable,
        include_default=include_default,
        include_deleted=include_deleted,
    )

    total_count = get_persona_count_for_user(
        user=user,
        db_session=db_session,
        get_editable=get_editable,
        include_default=include_default,
        include_deleted=include_deleted,
    )

    return PaginatedReturn(
        items=agents,
        total_items=total_count,
    )


@admin_router.patch("/{persona_id}/undelete", tags=PUBLIC_API_TAGS)
def undelete_persona(
    persona_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    mark_persona_as_not_deleted(
        persona_id=persona_id,
        user=user,
        db_session=db_session,
    )


# used for assistant profile pictures
@admin_router.post("/upload-image")
def upload_file(
    file: UploadFile,
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> dict[str, str]:
    file_store = get_default_file_store()
    file_type = ChatFileType.IMAGE
    file_id = file_store.save_file(
        content=file.file,
        display_name=file.filename,
        file_origin=FileOrigin.CHAT_UPLOAD,
        file_type=file.content_type or file_type.value,
    )
    return {"file_id": file_id}


# used for chatterbox reference audio
@basic_router.post("/upload-reference-audio")
def upload_reference_audio(
    file: UploadFile,
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> dict[str, str]:
    file_store = get_default_file_store()
    file_id = file_store.save_file(
        content=file.file,
        display_name=file.filename,
        file_origin=FileOrigin.CHAT_UPLOAD,
        file_type=file.content_type or "audio/wav",
    )
    return {"file_id": file_id}


"""Endpoints for all"""


@basic_router.post("", tags=PUBLIC_API_TAGS)
def create_persona(
    persona_upsert_request: PersonaUpsertRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> PersonaSnapshot:
    tenant_id = get_current_tenant_id()

    _validate_user_knowledge_enabled(persona_upsert_request, "create")
    _validate_vector_db_knowledge(persona_upsert_request)

    persona_snapshot = create_update_persona(
        persona_id=None,
        create_persona_request=persona_upsert_request,
        user=user,
        db_session=db_session,
    )
    mt_cloud_telemetry(
        tenant_id=tenant_id,
        distinct_id=str(user.id),
        event=MilestoneRecordType.CREATED_ASSISTANT,
    )

    return persona_snapshot


# NOTE: This endpoint cannot update persona configuration options that
# are core to the persona, such as its display priority and
# whether or not the assistant is a built-in / default assistant
@basic_router.patch("/{persona_id}", tags=PUBLIC_API_TAGS)
def update_persona(
    persona_id: int,
    persona_upsert_request: PersonaUpsertRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> PersonaSnapshot:
    _validate_user_knowledge_enabled(persona_upsert_request, "update")
    _validate_vector_db_knowledge(persona_upsert_request)

    persona_snapshot = create_update_persona(
        persona_id=persona_id,
        create_persona_request=persona_upsert_request,
        user=user,
        db_session=db_session,
    )
    return persona_snapshot


class PersonaLabelPatchRequest(BaseModel):
    label_name: str


@basic_router.get("/labels")
def get_labels(
    db: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> list[PersonaLabelResponse]:
    return [
        PersonaLabelResponse.from_model(label)
        for label in get_assistant_labels(db_session=db)
    ]


@basic_router.post("/labels")
def create_label(
    label: PersonaLabelCreate,
    db: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> PersonaLabelResponse:
    """Create a new assistant label"""
    try:
        label_model = create_assistant_label(name=label.name, db_session=db)
        return PersonaLabelResponse.from_model(label_model)
    except IntegrityError:
        raise HTTPException(
            status_code=400,
            detail=f"Label with name '{label.name}' already exists. Please choose a different name.",
        )


@admin_router.patch("/label/{label_id}")
def patch_persona_label(
    label_id: int,
    persona_label_patch_request: PersonaLabelPatchRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    update_persona_label(
        label_id=label_id,
        label_name=persona_label_patch_request.label_name,
        db_session=db_session,
    )


@admin_router.delete("/label/{label_id}")
def delete_label(
    label_id: int,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    delete_persona_label(label_id=label_id, db_session=db_session)


class PersonaUserShareRequest(BaseModel):
    user_id: UUID
    permission: PersonaSharePermission


class PersonaGroupShareRequest(BaseModel):
    group_id: int
    permission: PersonaSharePermission


class PersonaShareRequest(BaseModel):
    # Legacy id-lists: shares keep an existing row's level, new rows get VIEWER
    user_ids: list[UUID] | None = None
    group_ids: list[int] | None = None
    # Leveled shares: full replacement including permission levels
    user_shares: list[PersonaUserShareRequest] | None = None
    group_shares: list[PersonaGroupShareRequest] | None = None
    is_public: bool | None = None
    public_permission: PersonaSharePermission | None = None
    label_ids: list[int] | None = None

    @model_validator(mode="after")
    def _reject_legacy_and_leveled(self) -> "PersonaShareRequest":
        # A stale client sending both forms would silently lose the legacy list
        # (the leveled map wins downstream); reject the ambiguity at the boundary.
        if self.user_ids is not None and self.user_shares is not None:
            raise ValueError("Provide either user_ids or user_shares, not both")
        if self.group_ids is not None and self.group_shares is not None:
            raise ValueError("Provide either group_ids or group_shares, not both")
        return self


# We notify each user when a user is shared with them
@basic_router.patch("/{persona_id}/share")
def share_persona(
    persona_id: int,
    persona_share_request: PersonaShareRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    user_shares = (
        {share.user_id: share.permission for share in persona_share_request.user_shares}
        if persona_share_request.user_shares is not None
        else None
    )
    group_shares = (
        {
            share.group_id: share.permission
            for share in persona_share_request.group_shares
        }
        if persona_share_request.group_shares is not None
        else None
    )
    try:
        update_persona_shared(
            persona_id=persona_id,
            user=user,
            db_session=db_session,
            user_ids=persona_share_request.user_ids,
            group_ids=persona_share_request.group_ids,
            user_shares=user_shares,
            group_shares=group_shares,
            is_public=persona_share_request.is_public,
            public_permission=persona_share_request.public_permission,
            label_ids=persona_share_request.label_ids,
        )
    except PermissionError as e:
        logger.exception("Failed to share persona")
        raise HTTPException(status_code=403, detail=str(e))
    except NotImplementedError as e:
        logger.exception("Failed to share persona")
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        logger.exception("Failed to share persona")
        raise HTTPException(status_code=400, detail=str(e))


class TransferPersonaOwnershipRequest(BaseModel):
    new_owner_user_id: UUID | None = None
    new_owner_group_id: int | None = None


@basic_router.post("/{persona_id}/transfer-ownership")
def transfer_persona_ownership_endpoint(
    persona_id: int,
    transfer_request: TransferPersonaOwnershipRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    versioned_transfer = fetch_versioned_implementation(
        "onyx.db.persona", "transfer_persona_ownership"
    )
    try:
        versioned_transfer(
            persona_id=persona_id,
            user=user,
            db_session=db_session,
            new_owner_user_id=transfer_request.new_owner_user_id,
            new_owner_group_id=transfer_request.new_owner_group_id,
        )
    except PermissionError as e:
        logger.exception("Failed to transfer persona ownership")
        raise HTTPException(status_code=403, detail=str(e))
    except (ValueError, NotImplementedError) as e:
        logger.exception("Failed to transfer persona ownership")
        raise HTTPException(status_code=400, detail=str(e))


@basic_router.delete("/{persona_id}/share/me")
def leave_persona_shares(
    persona_id: int,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        remove_user_from_persona_shares(
            persona_id=persona_id,
            user=user,
            db_session=db_session,
        )
    except ValueError as e:
        logger.exception("Failed to remove user from persona shares")
        raise HTTPException(status_code=400, detail=str(e))


@basic_router.delete("/{persona_id}", tags=PUBLIC_API_TAGS)
def delete_persona(
    persona_id: int,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    mark_persona_as_deleted(
        persona_id=persona_id,
        user=user,
        db_session=db_session,
    )


@basic_router.get("")
def list_personas(
    user: User = Depends(current_chat_accessible_user),
    db_session: Session = Depends(get_session),
    include_deleted: bool = False,
    persona_ids: list[int] = Query(None),
) -> list[MinimalPersonaSnapshot]:
    personas = get_minimal_persona_snapshots_for_user(
        user=user,
        include_deleted=include_deleted,
        db_session=db_session,
        get_editable=False,
    )

    if persona_ids:
        personas = [p for p in personas if p.id in persona_ids]

    return personas


@agents_router.get("", tags=PUBLIC_API_TAGS)
def get_agents_paginated(
    page_num: int = Query(0, ge=0, description="Page number (0-indexed)."),
    page_size: int = Query(10, ge=1, le=1000, description="Items per page."),
    user: User = Depends(current_chat_accessible_user),
    db_session: Session = Depends(get_session),
    include_deleted: bool = Query(
        False, description="If true, includes deleted personas."
    ),
    get_editable: bool = Query(
        False, description="If true, only returns editable personas."
    ),
    include_default: bool = Query(
        True, description="If true, includes builtin/default personas."
    ),
) -> PaginatedReturn[MinimalPersonaSnapshot]:
    """Paginated endpoint for listing agents available to the user.

    Returns items for the requested page plus total count.
    Personas are ordered by display_priority (ASC, nulls last) then by ID (ASC).

    NOTE: persona_ids filter is not supported with pagination. Use the
    non-paginated endpoint if filtering by specific IDs is needed.
    """
    agents = get_minimal_persona_snapshots_paginated(
        user=user,
        db_session=db_session,
        page_num=page_num,
        page_size=page_size,
        get_editable=get_editable,
        include_default=include_default,
        include_deleted=include_deleted,
    )

    total_count = get_persona_count_for_user(
        user=user,
        db_session=db_session,
        get_editable=get_editable,
        include_default=include_default,
        include_deleted=include_deleted,
    )

    return PaginatedReturn(
        items=agents,
        total_items=total_count,
    )


@basic_router.get("/explore")
def explore_personas(
    query: str | None = None,
    category: str | None = None,
    sort_by: str = "rating",
    tab: str = "all",
    page_num: int = 0,
    page_size: int = 20,
    user: User | None = Depends(current_chat_accessible_user),
    db_session: Session = Depends(get_session),
) -> PaginatedReturn[MinimalPersonaSnapshot]:
    personas, total = get_explore_personas_paginated(
        user=user,
        db_session=db_session,
        query=query,
        category=category,
        sort_by=sort_by,
        page_num=page_num,
        page_size=page_size,
        tab=tab,
    )
    user_group_ids: set[int] = (
        get_user_group_ids_for_user(db_session, user.id) if user is not None else set()
    )

    def _snapshot(p: Persona) -> MinimalPersonaSnapshot:
        permission = (
            get_persona_access_level(p, user, user_group_ids)
            if user is not None
            else None
        )
        return MinimalPersonaSnapshot.from_model(p, user_permission=permission)

    return PaginatedReturn(
        items=[_snapshot(p) for p in personas],
        total_items=total,
    )


@basic_router.get("/categories")
def get_categories(
    _: User | None = Depends(current_chat_accessible_user),
    db_session: Session = Depends(get_session),
) -> list[str]:
    from sqlalchemy import select
    from onyx.db.models import Persona
    stmt = select(Persona.category).where(
        Persona.category.is_not(None), 
        Persona.deleted == False
    ).distinct()
    categories = db_session.scalars(stmt).all()
    return sorted(list(categories))


@basic_router.get("/{persona_id}", tags=PUBLIC_API_TAGS)
def get_persona(
    persona_id: int,
    user: User = Depends(current_limited_user),
    db_session: Session = Depends(get_session),
) -> FullPersonaSnapshot:
    user_group_ids: set[int] = (
        get_user_group_ids_for_user(db_session, user.id) if user is not None else set()
    )
    persona = get_persona_by_id(
        persona_id=persona_id,
        user=user,
        db_session=db_session,
        is_for_edit=False,
        user_group_ids=user_group_ids,
    )

    # Validate and clear the model override if the referenced model is no longer
    # accessible to this persona (e.g. provider was restricted after the persona was saved).
    if persona.default_model_configuration_id:
        valid_ids = get_valid_model_configuration_ids_for_persona(
            persona, user, db_session
        )
        if persona.default_model_configuration_id not in valid_ids:
            persona.default_model_configuration_id = None
            db_session.commit()

    snapshot = FullPersonaSnapshot.from_model(persona)
    if user is not None:
        snapshot.user_permission = get_persona_access_level(
            persona, user, user_group_ids
        )
        from onyx.db.models import PersonaFavorite
        snapshot.is_favorite = db_session.query(PersonaFavorite).filter_by(
            user_id=user.id, persona_id=persona_id
        ).first() is not None
    snapshot.admin_count = get_active_admin_count(db_session)
    snapshot.ownership_vacant = persona_ownership_is_vacant(persona)
    return snapshot


@basic_router.get("/{persona_id}/avatar")
def get_persona_avatar(
    persona_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    # Mirror `fetch_chat_file`: return 404 (not 403) for any failure so
    # callers cannot probe persona existence or avatar ownership.
    try:
        persona = get_persona_by_id(
            persona_id=persona_id,
            user=user,
            db_session=db_session,
            is_for_edit=False,
        )
    except ValueError:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Avatar not found")

    file_id = persona.uploaded_image_id
    if not file_id:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Avatar not found")

    # Defense-in-depth: reject file_ids that weren't produced by the
    # avatar upload endpoint, so a crafted PATCH cannot rebind a persona
    # to another user's USER_FILE / CHAT_IMAGE_GEN asset.
    file_record = get_filerecord_by_file_id_optional(file_id, db_session)
    if not file_record:
        logger.warning(
            "Persona %s references avatar file %s with no matching FileRecord; rejecting.",
            persona_id,
            file_id,
        )
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Avatar not found")
    if file_record.file_origin != FileOrigin.CHAT_UPLOAD:
        logger.warning(
            "Persona %s avatar references file %s with unexpected origin %s; rejecting.",
            persona_id,
            file_id,
            file_record.file_origin,
        )
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Avatar not found")

    etag = f'"{file_id}"'
    cache_headers = {
        "Cache-Control": "private, max-age=31536000, immutable",
        "ETag": etag,
        "Vary": "Cookie",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache_headers)

    file_store = get_default_file_store()
    file_io = file_store.read_file(file_id, mode="b")
    return StreamingResponse(
        file_io, media_type=file_record.file_type, headers=cache_headers
    )

@basic_router.get("/image/{file_id}")
def get_persona_image_by_id(
    file_id: str,
    request: Request,
    user: User | None = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    file_record = get_filerecord_by_file_id_optional(file_id, db_session)
    if not file_record or file_record.file_origin != FileOrigin.CHAT_UPLOAD:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Image not found")
        
    etag = f'"{file_id}"'
    cache_headers = {
        "Cache-Control": "private, max-age=31536000, immutable",
        "ETag": etag,
        "Vary": "Cookie",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache_headers)

    file_store = get_default_file_store()
    file_io = file_store.read_file(file_id, mode="b")
    return StreamingResponse(
        file_io, media_type=file_record.file_type, headers=cache_headers
    )


@basic_router.get("/{persona_id}/reference-audio")
def get_persona_reference_audio(
    persona_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    try:
        persona = get_persona_by_id(
            persona_id=persona_id,
            user=user,
            db_session=db_session,
            is_for_edit=False,
        )
    except ValueError:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Reference audio not found")

    file_id = persona.reference_audio_id
    if not file_id:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Reference audio not found")

    file_record = get_filerecord_by_file_id_optional(file_id, db_session)
    if not file_record:
        logger.warning(
            "Persona %s references audio file %s with no matching FileRecord; rejecting.",
            persona_id,
            file_id,
        )
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Reference audio not found")

    etag = f'"{file_id}"'
    cache_headers = {
        "Cache-Control": "private, max-age=31536000, immutable",
        "ETag": etag,
        "Vary": "Cookie",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache_headers)

    file_store = get_default_file_store()
    file_io = file_store.read_file(file_id, mode="b")
    return StreamingResponse(
        file_io, media_type=file_record.file_type, headers=cache_headers
    )

class RatingRequest(BaseModel):
    rating: int

@basic_router.post("/{persona_id}/rate")
def rate_persona_endpoint(
    persona_id: int,
    request: RatingRequest,
    user: User = Depends(current_chat_accessible_user),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    if request.rating < 1 or request.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    rate_persona(db_session, persona_id, user.id, request.rating)
    return {"success": True}

@basic_router.post("/{persona_id}/favorite")
def favorite_persona_endpoint(
    persona_id: int,
    user: User = Depends(current_chat_accessible_user),
    db_session: Session = Depends(get_session),
) -> dict[str, bool]:
    is_favorited = toggle_persona_favorite(db_session, persona_id, user.id)
    # Return whether the persona is favorited after the toggle. 
    # Can deduce this from the db but for now, we just return true.
    return {"success": True}

import requests
import io
import mimetypes
from onyx.file_store.file_store import get_default_file_store
from onyx.configs.constants import FileOrigin

def _fetch_persona_image(query: str) -> str | None:
    try:
        searxng_url = "http://searxng:8080/search"
        resp = requests.get(searxng_url, params={"q": query, "categories": "images", "format": "json"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        for res in results:
            img_url = res.get("img_src")
            if not img_url:
                continue
            
            img_resp = requests.get(img_url, timeout=10)
            if img_resp.status_code == 200:
                content_type = img_resp.headers.get("Content-Type", "image/jpeg")
                ext = mimetypes.guess_extension(content_type) or ".jpg"
                display_name = f"persona_avatar{ext}"
                
                file_store = get_default_file_store()
                file_id = file_store.save_file(
                    content=io.BytesIO(img_resp.content),
                    display_name=display_name,
                    file_origin=FileOrigin.CHAT_UPLOAD,
                    file_type=content_type,
                )
                return file_id
    except Exception as e:
        logger.error(f"Failed to fetch persona image: {e}")
    return None

def _generate_reference_audio(text: str, voice_profile: str) -> str | None:
    try:
        # Default fallback text if empty
        if not text:
            text = "Hello there! I am your new AI assistant."
        
        qwen3_tts_url = "http://qwen3_tts:8000/audio/speech"
        resp = requests.post(
            qwen3_tts_url,
            json={
                "text": text,
                "voice": "default",
                "speed": 1.0,
                "instruct": voice_profile,
            },
            timeout=30
        )
        resp.raise_for_status()
        
        file_store = get_default_file_store()
        file_id = file_store.save_file(
            content=io.BytesIO(resp.content),
            display_name="reference_audio.wav",
            file_origin=FileOrigin.CHAT_UPLOAD,
            file_type="audio/wav",
        )
        return file_id
    except Exception as e:
        logger.warning(f"Failed to generate reference audio: {e}")
    return None

@admin_router.post("/auto-generate")
def auto_generate_persona(
    request: PersonaAutoGenerateRequest,
    user: User | None = Depends(current_curator_or_admin_user),
) -> PersonaAutoGenerateResponse:
    llm = get_default_llm()
    prompt = f"""
You are an expert persona and AI character designer.
The user wants to create a character with the following name and description:
Name: {request.name}
Description: {request.description}

Generate the detailed configuration for this persona in JSON format.
Your output MUST be ONLY valid JSON matching the following schema. Do not wrap in markdown code blocks.

Schema:
{{
  "description": "A short, punchy 1-2 sentence description of who the persona is (e.g. A helpful coding assistant).",
  "voice_gender": "The gender of the voice. MUST BE EXACTLY one of: 'male', 'female', or 'unisex'.",
  "instructions": "Detailed system prompt defining personality, role, and instructions.",
  "pb_backstory": "A short summary of who they are and their background.",
  "pb_traits": "Comma-separated list of core personality traits.",
  "pb_goals": "Comma-separated list of their main goals or motivations.",
  "pb_tone": "How they speak, format, and tone (e.g. enthusiastic, sarcastic).",
  "pb_voice_profile": "A short description of how their voice sounds.",
  "starter_messages": ["A list of 3-4 example starter messages from the persona's perspective."],
  "reminders": "A task prompt or short reminders for the persona (can be empty string).",
  "replace_base_system_prompt": false,
  "pb_filler_words": "Comma-separated list of filler words or phrases they use.",
  "pb_complexity": "Vocabulary complexity (e.g. 'simple', 'advanced', 'academic').",
  "knowledge_cutoff_date": null,
  "icon_name": null,
  "image_generation": "Set to true if this persona should be able to generate images.",
  "web_search": "Set to true if this persona should be able to search the live web.",
  "open_url": "Set to true if this persona should be able to read specific URLs.",
  "code_interpreter": "Set to true if this persona should be able to run code.",
  "coding_agent": "Set to true if this persona should be a coding agent."
}}
"""
    try:
        response = llm.invoke([UserMessage(content=prompt)])
        raw_content = response.choice.message.content.strip() if response.choice.message.content else ""
        # strip markdown code blocks if any
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
        if raw_content.startswith("```"):
            raw_content = raw_content[3:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
        
        parsed = json.loads(raw_content.strip())
        
        import concurrent.futures
        uploaded_image_id = None
        reference_audio_id = None
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_img = executor.submit(_fetch_persona_image, request.name)
            
            starter_msgs = parsed.get("starter_messages", [])
            audio_text = starter_msgs[0] if starter_msgs else parsed.get("description", "Hello!")
            voice_profile = parsed.get("pb_voice_profile", "")
            
            future_audio = executor.submit(_generate_reference_audio, audio_text, voice_profile)
            
            uploaded_image_id = future_img.result()
            reference_audio_id = future_audio.result()

        return PersonaAutoGenerateResponse(
            description=parsed.get("description", ""),
            voice_gender=parsed.get("voice_gender", "unisex"),
            instructions=parsed.get("instructions", ""),
            pb_backstory=parsed.get("pb_backstory", ""),
            pb_traits=parsed.get("pb_traits", ""),
            pb_goals=parsed.get("pb_goals", ""),
            pb_tone=parsed.get("pb_tone", ""),
            pb_voice_profile=parsed.get("pb_voice_profile", ""),
            starter_messages=parsed.get("starter_messages", []),
            reminders=parsed.get("reminders", ""),
            replace_base_system_prompt=parsed.get("replace_base_system_prompt", False),
            pb_filler_words=parsed.get("pb_filler_words", ""),
            pb_complexity=parsed.get("pb_complexity", ""),
            knowledge_cutoff_date=parsed.get("knowledge_cutoff_date"),
            icon_name=parsed.get("icon_name"),
            uploaded_image_id=uploaded_image_id,
            reference_audio_id=reference_audio_id,
            image_generation=parsed.get("image_generation", False),
            web_search=parsed.get("web_search", False),
            open_url=parsed.get("open_url", False),
            code_interpreter=parsed.get("code_interpreter", False),
            coding_agent=parsed.get("coding_agent", False),

        )
    except Exception as e:
        logger.error(f"Failed to auto-generate persona: {e}")
        raise OnyxError(OnyxErrorCode.INTERNAL_ERROR, "Failed to auto-generate persona details")
