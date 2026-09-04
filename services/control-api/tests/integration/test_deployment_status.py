"""What the settings page may show, and to whom.

Two things are being guarded. The page exists so an operator can see what
Primer was pointed at without reading a values file and three sets of
container logs - and the addresses it shows routinely carry passwords,
because that is how PostgreSQL and RabbitMQ URLs are written.
"""

from __future__ import annotations

from control_support import UserClient
from primer_control.routes.admin import without_credentials


class TestStrippingCredentialsFromAUrl:
    """Removed, not masked. A settings page is a thing people screenshot."""

    def test_a_password_is_removed(self) -> None:
        cleaned = without_credentials("postgresql://primer:hunter2@db:5432/primer") or ""

        assert "hunter2" not in cleaned
        assert cleaned == "postgresql://db:5432/primer"

    def test_the_username_goes_with_it(self) -> None:
        """It is half a credential, and it is not what an operator is checking."""
        assert without_credentials("amqp://user:pw@broker:5672/") == "amqp://broker:5672/"

    def test_nothing_is_starred_out(self) -> None:
        """A masked secret still says how long it was."""
        cleaned = (
            without_credentials("postgresql://primer:a-very-long-password@db:5432/primer") or ""
        )

        assert "*" not in cleaned
        assert "•" not in cleaned

    def test_a_url_with_no_credential_is_left_alone(self) -> None:
        assert without_credentials("http://chat:8000") == "http://chat:8000"

    def test_a_password_containing_an_at_sign_is_still_removed(self) -> None:
        """The host is after the last @, not the first."""
        cleaned = without_credentials("postgresql://primer:p@ss@db:5432/primer")

        assert cleaned == "postgresql://db:5432/primer"

    def test_nothing_configured_stays_nothing(self) -> None:
        assert without_credentials(None) is None


class TestWhenNobodyHasBeenNamedAnAdministrator:
    """Fails closed, which is the property worth pinning.

    The client these tests run against has authentication on and names no
    administrator group - the state a deployment is in before an operator
    has made the decision. Everyone is refused, rather than everyone being
    allowed to repoint the deployment.

    403 rather than 404: a settings page is restricted, not secret, and
    telling an ordinary user "not for you" is more useful than pretending
    the page does not exist.
    """

    async def test_an_authenticated_user_is_refused(self, owner: UserClient) -> None:
        response = await owner.get("/api/v1/admin/status")

        assert response.status_code == 403
        assert response.json()["code"] == "identity_invalid"

    async def test_the_refusal_says_why(self, owner: UserClient) -> None:
        assert "administrator" in (await owner.get("/api/v1/admin/status")).json()["detail"]
