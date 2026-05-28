from flask import Blueprint, render_template, request, jsonify, g
from flask_login import login_required, current_user
from app import db
from app.models import AgentMessage
from app.agent.accountant import run_agent
from app.services.permissions import require_permission

bp = Blueprint("agent", __name__)


@bp.route("/")
@login_required
def index():
    history = AgentMessage.query.filter_by(
        company_id=g.active_company.id, user_id=current_user.id
    ).order_by(AgentMessage.created_at).limit(40).all()
    return render_template("agent/chat.html", history=history)


@bp.route("/chat", methods=["POST"])
@login_required
@require_permission("agent.use")
def chat():
    user_msg = (request.json or {}).get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "رسالة فارغة"}), 400
    if not g.active_company:
        return jsonify({"error": "لا توجد شركة نشطة"}), 400

    # Persist user message
    db.session.add(AgentMessage(
        company_id=g.active_company.id, user_id=current_user.id,
        role="user", content=user_msg,
    ))
    db.session.commit()

    # Load recent history (last 20 turns)
    history = AgentMessage.query.filter_by(
        company_id=g.active_company.id, user_id=current_user.id
    ).order_by(AgentMessage.created_at.desc()).limit(20).all()
    history.reverse()

    messages = [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")]

    company_context = (
        f"اسم الشركة: {g.active_company.name}\n"
        f"العملة الأساسية: {g.active_company.base_currency}\n"
        f"نسبة الضريبة: {g.active_company.vat_rate}%\n"
    )

    try:
        reply, _, tool_trace = run_agent(
            messages, g.active_company.id, current_user.id, company_context=company_context
        )
        db.session.add(AgentMessage(
            company_id=g.active_company.id, user_id=current_user.id,
            role="assistant", content=reply,
        ))
        db.session.commit()
        return jsonify({"reply": reply, "tools": tool_trace})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/clear", methods=["POST"])
@login_required
@require_permission("agent.use")
def clear():
    AgentMessage.query.filter_by(
        company_id=g.active_company.id, user_id=current_user.id
    ).delete()
    db.session.commit()
    return jsonify({"ok": True})
