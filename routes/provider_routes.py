"""
Routes for managing AI providers.
"""

import logging
from typing import Tuple, Optional, Dict, Any
from flask import Blueprint, render_template, redirect, url_for, flash, request, make_response
from werkzeug.wrappers import Response
from flask_login import login_required
from sqlalchemy import text, Result
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.engine.row import Row

from database import db_session
from decorators import admin_required
from forms import ProviderForm

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
bp = Blueprint("provider", __name__)

@bp.route("/providers/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_provider() -> Response:
    """Handle adding a new provider."""
    form = ProviderForm()

    if request.method == "POST" and form.validate_on_submit():
        try:
            with db_session() as db:
                # Check for existing provider with same name or slug
                check_query: TextClause = text(
                    """
                    SELECT name, slug
                    FROM providers
                    WHERE LOWER(name) = LOWER(:name)
                    OR LOWER(slug) = LOWER(:slug)
                """
                )
                existing: Optional[Row] = db.execute(
                    check_query,
                    {
                        "name": form.name.data or "",
                        "slug": form.slug.data or ""
                    },
                ).fetchone()

                if existing:
                    field = (
                        "name"
                        if existing[0].lower() == (form.name.data or "").lower()
                        else "slug"
                    )
                    flash(f"A provider with this {field} already exists", "error")
                    return make_response(render_template("add_provider.html", form=form))

                # Insert new provider
                query: TextClause = text(
                    """
                    INSERT INTO providers (
                        name, slug, api_base_url, capabilities, requires_authentication,
                        api_version_format, created_at
                    ) VALUES (
                        :name, :slug, :api_base_url, :capabilities, :requires_authentication,
                        :api_version_format, NOW()
                    )
                    RETURNING id
                """
                )
                result: Result = db.execute(
                    query,
                    {
                        "name": form.name.data or "",
                        "slug": form.slug.data or "",
                        "api_base_url": (form.api_base_url.data or "").rstrip("/"),
                        "capabilities": "{}",  # Default empty JSON capabilities
                        "requires_authentication": form.requires_authentication.data or False,
                        "api_version_format": None  # Default null api_version_format
                    },
                )
                provider_id: Optional[int] = result.scalar()

                if not provider_id:
                    raise ValueError("Failed to create provider - no ID returned")

                db.commit()
                flash(f"Provider {form.name.data} added successfully", "success")
                return redirect(url_for("model.add_model"))

        except Exception as e:
            logger.error("Error creating provider: %s", str(e), exc_info=True)
            flash(f"Error creating provider: {str(e)}", "error")
            return make_response(render_template("add_provider.html", form=form))

    return make_response(render_template("add_provider.html", form=form))

@bp.route("/providers")
@login_required
@admin_required
def list_providers() -> Response:
    """List all providers."""
    try:
        with db_session() as db:
            query: TextClause = text(
                """
                SELECT p.*, COUNT(m.id) as model_count
                FROM providers p
                LEFT JOIN models m ON p.id = m.provider_id
                GROUP BY p.id
                ORDER BY p.name
                """
            )
            providers: list[Dict[str, Any]] = db.execute(query).mappings().all()
            return make_response(render_template(
                "list_providers.html",
                providers=providers
            ))
    except Exception as e:
        logger.error("Error listing providers: %s", str(e), exc_info=True)
        flash("Error retrieving providers", "error")
        return redirect(url_for("chat.chat_interface"))

@bp.route("/providers/<int:provider_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_provider(provider_id: int) -> Response:
    """Edit an existing provider."""
    form = ProviderForm()

    try:
        with db_session() as db:
            # Get existing provider
            query: TextClause = text(
                """
                SELECT * FROM providers WHERE id = :provider_id
                """
            )
            provider: Optional[Row] = db.execute(
                query, {"provider_id": provider_id}
            ).fetchone()

            if not provider:
                flash("Provider not found", "error")
                return redirect(url_for("provider.list_providers"))

            if request.method == "POST" and form.validate_on_submit():
                # Update provider
                update_query: TextClause = text(
                    """
                    UPDATE providers
                    SET name = :name,
                        slug = :slug,
                        api_base_url = :api_base_url,
                        requires_authentication = :requires_authentication
                    WHERE id = :provider_id
                    """
                )
                db.execute(
                    update_query,
                    {
                        "name": form.name.data or "",
                        "slug": form.slug.data or "",
                        "api_base_url": (form.api_base_url.data or "").rstrip("/"),
                        "requires_authentication": form.requires_authentication.data or False,
                        "provider_id": provider_id
                    },
                )
                db.commit()
                flash("Provider updated successfully", "success")
                return redirect(url_for("provider.list_providers"))

            # Pre-populate form with existing data
            form.name.data = provider.name
            form.slug.data = provider.slug
            form.api_base_url.data = provider.api_base_url
            form.requires_authentication.data = provider.requires_authentication

    except Exception as e:
        logger.error("Error editing provider: %s", str(e), exc_info=True)
        flash(f"Error editing provider: {str(e)}", "error")

    return make_response(render_template("edit_provider.html", form=form))

@bp.route("/providers/<int:provider_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_provider(provider_id: int) -> Response:
    """Delete a provider."""
    try:
        with db_session() as db:
            # Check if provider has associated models
            check_query: TextClause = text(
                """
                SELECT COUNT(*) as model_count
                FROM models
                WHERE provider_id = :provider_id
                """
            )
            result = db.execute(check_query, {"provider_id": provider_id}).fetchone()

            if result and result.model_count > 0:
                flash("Cannot delete provider with associated models", "error")
                return redirect(url_for("provider.list_providers"))

            # Delete provider
            delete_query: TextClause = text(
                """
                DELETE FROM providers WHERE id = :provider_id
                """
            )
            db.execute(delete_query, {"provider_id": provider_id})
            db.commit()
            flash("Provider deleted successfully", "success")

    except Exception as e:
        logger.error("Error deleting provider: %s", str(e), exc_info=True)
        flash(f"Error deleting provider: {str(e)}", "error")

    return redirect(url_for("provider.list_providers"))
