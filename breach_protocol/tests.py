from django.test import SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage"
)
class BreachProtocolPageTests(SimpleTestCase):
    def test_page_is_available(self) -> None:
        response = self.client.get(reverse("breach_protocol:game"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Взлом протокола")
        self.assertContains(response, 'id="code-matrix"')
        self.assertContains(response, "breach_protocol/js/game.js")

    def test_settings_have_required_limits(self) -> None:
        response = self.client.get(reverse("breach_protocol:game"))

        self.assertContains(response, 'id="grid-size" name="grid-size" type="number" min="3" max="10"')
        self.assertContains(response, 'id="sequence-length" name="sequence-length" type="number" min="2" max="8"')
        self.assertContains(response, 'id="symbol-count" name="symbol-count" type="number" min="2"')
