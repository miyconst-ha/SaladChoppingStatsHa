"""Test the acknowledgement gate in isolation without a Home Assistant runtime."""

import ast
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock


ROOT = Path(__file__).resolve().parents[1]


class AcknowledgementTests(unittest.TestCase):
    def setUp(self):
        source = ROOT / "custom_components/salad_chopping/config_flow.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        flow = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        method = next(node for node in flow.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_cookie_step")
        self.session = Mock()
        self.create_session = Mock(return_value=self.session)
        self.client = Mock(account_id=AsyncMock(return_value="account"), earnings=AsyncMock())
        self.make_client = Mock(return_value=self.client)
        namespace = {
            "CONF_AUTH_COOKIE": "auth_cookie",
            "CONF_ACKNOWLEDGE_RISKS": "acknowledge_risks",
            "ConfigFlowResult": dict,
            "COOKIE_SCHEMA": object(),
            "async_create_clientsession": self.create_session,
            "DummyCookieJar": Mock(),
            "SaladClient": self.make_client,
            "SaladAuthError": type("AuthError", (Exception,), {}),
            "SaladError": type("ApiError", (Exception,), {}),
        }
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
        self.method = namespace["_async_cookie_step"]
        self.flow = Mock()
        self.flow.async_set_unique_id = AsyncMock()
        self.flow.async_show_form.side_effect = lambda **kwargs: kwargs

    def run_step(self, step, data):
        # All awaited operations are completed AsyncMocks, so no network or
        # event loop is needed to exercise this method's control flow.
        coroutine = self.method(self.flow, step, data)
        with self.assertRaises(StopIteration) as result:
            coroutine.send(None)
        return result.exception.value

    def test_missing_false_and_non_boolean_acknowledgements_block_network(self):
        for step in ("user", "reauth_confirm"):
            for value in (None, False, "true", 1):
                with self.subTest(step=step, value=value):
                    data = {"auth_cookie": "test-cookie"}
                    if value is not None:
                        data["acknowledge_risks"] = value
                    result = self.run_step(step, data)
                    self.assertEqual(result["errors"], {"acknowledge_risks": "acknowledgement_required"})
                    self.create_session.assert_not_called()
                    self.make_client.assert_not_called()

    def test_initial_form_does_not_open_a_session(self):
        result = self.run_step("user", None)
        self.assertEqual(result["errors"], {})
        self.create_session.assert_not_called()

    def test_acceptance_allows_setup_and_stores_only_cookie(self):
        self.run_step("user", {"auth_cookie": " test-cookie ", "acknowledge_risks": True})
        self.client.account_id.assert_awaited_once()
        self.flow.async_create_entry.assert_called_once_with(title="Salad Chopping Statistics", data={"auth_cookie": "test-cookie"})
        self.session.detach.assert_called_once()

    def test_acceptance_allows_reauthentication(self):
        self.run_step("reauth_confirm", {"auth_cookie": "new-cookie", "acknowledge_risks": True})
        self.flow._abort_if_unique_id_mismatch.assert_called_once()
        self.flow.async_update_reload_and_abort.assert_called_once_with(self.flow._get_reauth_entry(), data_updates={"auth_cookie": "new-cookie"})
        self.session.detach.assert_called_once()


if __name__ == "__main__":
    unittest.main()
