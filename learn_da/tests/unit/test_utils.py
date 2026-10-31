"""
工具类单元测试（纯函数，无 IO，无 fixture 依赖）
"""

from app.utils.base_response import StdResp


# ──────────────────────────────────────────────
# StdResp 测试
# ──────────────────────────────────────────────

class TestStdResp:
    def test_success_default(self):
        resp = StdResp.success()
        assert resp.code == 200
        assert resp.msg == "success"
        assert resp.data is None

    def test_success_with_data(self):
        resp = StdResp.success(data={"id": 1}, msg="OK")
        assert resp.code == 200
        assert resp.data == {"id": 1}
        assert resp.msg == "OK"

    def test_error_default(self):
        resp = StdResp.error(msg="出错了")
        assert resp.code == 400
        assert resp.msg == "出错了"

    def test_error_custom_code(self):
        resp = StdResp.error(msg="未找到", code=404)
        assert resp.code == 404

    def test_not_found(self):
        resp = StdResp.not_found()
        assert resp.code == 404

    def test_unauthorized(self):
        resp = StdResp.unauthorized()
        assert resp.code == 401

    def test_forbidden(self):
        resp = StdResp.forbidden()
        assert resp.code == 403

    def test_server_error(self):
        resp = StdResp.server_error()
        assert resp.code == 500

    def test_to_response_status_code(self):
        """to_response() 应返回与 code 一致的 HTTP 状态码"""
        json_resp = StdResp.error(msg="forbidden", code=403).to_response()
        assert json_resp.status_code == 403

    def test_camel_case_serialization(self):
        """字段名应自动转为驼峰"""
        resp = StdResp.success(data={"user_id": 1})
        body = resp.model_dump(by_alias=True)
        assert "code" in body
        assert "msg" in body
        assert "data" in body
