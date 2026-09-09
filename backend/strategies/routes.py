"""
Strategies admin-dashboard HTTP routes (docs/prd/admin-strategies-dashboard.md).
Factory pattern (create_strategies_blueprint), same reason as payments/routes.py:
require_role/current_user live in server.py, so a module-level Blueprint
importing them at load time would be circular.
"""
from flask import Blueprint, request, jsonify

from . import registry, service


def create_strategies_blueprint(require_role, current_user):
    bp = Blueprint("strategies", __name__)

    @bp.route("/api/strategies", methods=["GET"])
    @require_role("super_admin", "admin")
    def api_list_strategies():
        return jsonify(strategies=service.list_strategies())

    @bp.route("/api/strategies/<strategy_id>/config", methods=["GET"])
    @require_role("super_admin", "admin")
    def api_get_strategy_config(strategy_id):
        if registry.get_provider(strategy_id) is None:
            return jsonify(ok=False, error=f"unknown strategy_id: {strategy_id}"), 404
        return jsonify(config=service.get_config(strategy_id))

    @bp.route("/api/strategies/<strategy_id>/config", methods=["POST"])
    @require_role("super_admin", "admin")
    def api_set_strategy_config(strategy_id):
        if registry.get_provider(strategy_id) is None:
            return jsonify(ok=False, error=f"unknown strategy_id: {strategy_id}"), 404
        data = request.json or {}
        start_date = data.get("start_date")
        if not start_date:
            return jsonify(ok=False, error="start_date required"), 400
        try:
            service.set_config(strategy_id, start_date, data.get("params"), current_user()["email"])
        except ValueError as e:
            return jsonify(ok=False, error=str(e)), 400
        return jsonify(ok=True)

    @bp.route("/api/strategies/<strategy_id>/run", methods=["GET"])
    @require_role("super_admin", "admin")
    def api_run_strategy(strategy_id):
        if registry.get_provider(strategy_id) is None:
            return jsonify(ok=False, error=f"unknown strategy_id: {strategy_id}"), 404
        cfg = service.get_config(strategy_id)
        if cfg is None:
            return jsonify(ok=False, error="not configured — POST .../config first"), 400
        end_date = request.args.get("end_date")
        try:
            result = service.run_strategy(strategy_id, cfg["start_date"], end_date, cfg["params"])
        except LookupError as e:
            return jsonify(ok=False, error=str(e)), 404
        return jsonify(ok=True, **result)

    return bp
