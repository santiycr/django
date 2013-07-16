import base64
import httplib
import json
import os
import sys
from unittest import SkipTest

from django.test import LiveServerTestCase
from django.utils.module_loading import import_by_path
from django.utils.translation import ugettext as _


class AdminSeleniumWebDriverTestCase(LiveServerTestCase):

    available_apps = [
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.sites',
    ]
    webdriver_class = 'selenium.webdriver.firefox.webdriver.WebDriver'

    def setUp(self):
        if not os.environ.get('DJANGO_SELENIUM_TESTS', False):
            raise SkipTest('Selenium tests not requested')
        try:
            webdriver_class = import_by_path(self.webdriver_class)
        except Exception as e:
            raise SkipTest('Selenium webdriver "%s" not installed or not '
                           'operational: %s' % (self.webdriver_class, str(e)))

        from selenium.webdriver import Remote
        if webdriver_class is Remote:
            if not (os.environ.get('REMOTE_USER') and os.environ.get('REMOTE_KEY')):
                raise self.failureException('Both REMOTE_USER and REMOTE_KEY environment variables are required for remote tests.')
            capabilities = self.remote_capabilities.copy()
            capabilities['name'] = self.id()
            auth = '%(REMOTE_USER)s:%(REMOTE_KEY)s' % os.environ
            hub = os.environ.get('REMOTE_HUB', 'ondemand.saucelabs.com:80')
            self.selenium = Remote(
                command_executor='http://%s@%s/wd/hub' % (auth, hub),
                desired_capabilities=capabilities)
        else:
            self.selenium = webdriver_class()

        super(AdminSeleniumWebDriverTestCase, self).setUp()

    def tearDown(self):
        if hasattr(self, 'selenium'):
            from selenium.webdriver import Remote
            if isinstance(self.selenium, Remote):
                self._report_sauce_pass_fail()
            self.selenium.quit()
        super(AdminSeleniumWebDriverTestCase, self).tearDown()

    def _report_sauce_pass_fail(self):
        # Sauce Labs has no way of knowing if the test passed or failed, so we
        # let it know.
        base64string = base64.encodestring(
            '%s:%s' % (os.environ.get('REMOTE_USER'), os.environ.get('REMOTE_KEY')))[:-1]
        result = json.dumps({'passed': sys.exc_info() == (None, None, None)})
        url = '/rest/v1/%s/jobs/%s' % (os.environ.get('REMOTE_USER'), self.selenium.session_id)
        connection = httplib.HTTPConnection('saucelabs.com')
        connection.request(
            'PUT', url, result, headers={"Authorization": 'Basic %s' % base64string})
        result = connection.getresponse()
        return result.status == 200

    def wait_until(self, callback, timeout=10):
        """
        Helper function that blocks the execution of the tests until the
        specified callback returns a value that is not falsy. This function can
        be called, for example, after clicking a link or submitting a form.
        See the other public methods that call this function for more details.
        """
        from selenium.webdriver.support.wait import WebDriverWait
        WebDriverWait(self.selenium, timeout).until(callback)

    def wait_loaded_tag(self, tag_name, timeout=10):
        """
        Helper function that blocks until the element with the given tag name
        is found on the page.
        """
        self.wait_until(
            lambda driver: driver.find_element_by_tag_name(tag_name),
            timeout
        )

    def wait_page_loaded(self):
        """
        Block until page has started to load.
        """
        from selenium.common.exceptions import TimeoutException
        try:
            # Wait for the next page to be loaded
            self.wait_loaded_tag('body')
        except TimeoutException:
            # IE7 occasionnally returns an error "Internet Explorer cannot
            # display the webpage" and doesn't load the next page. We just
            # ignore it.
            pass

    def admin_login(self, username, password, login_url='/admin/'):
        """
        Helper function to log into the admin.
        """
        self.selenium.get('%s%s' % (self.live_server_url, login_url))
        username_input = self.selenium.find_element_by_name('username')
        username_input.send_keys(username)
        password_input = self.selenium.find_element_by_name('password')
        password_input.send_keys(password)
        login_text = _('Log in')
        self.selenium.find_element_by_xpath(
            '//input[@value="%s"]' % login_text).click()
        self.wait_page_loaded()

    def get_css_value(self, selector, attribute):
        """
        Helper function that returns the value for the CSS attribute of an
        DOM element specified by the given selector. Uses the jQuery that ships
        with Django.
        """
        return self.selenium.execute_script(
            'return django.jQuery("%s").css("%s")' % (selector, attribute))

    def get_select_option(self, selector, value):
        """
        Returns the <OPTION> with the value `value` inside the <SELECT> widget
        identified by the CSS selector `selector`.
        """
        from selenium.common.exceptions import NoSuchElementException
        options = self.selenium.find_elements_by_css_selector('%s > option' % selector)
        for option in options:
            if option.get_attribute('value') == value:
                return option
        raise NoSuchElementException('Option "%s" not found in "%s"' % (value, selector))

    def assertSelectOptions(self, selector, values):
        """
        Asserts that the <SELECT> widget identified by `selector` has the
        options with the given `values`.
        """
        options = self.selenium.find_elements_by_css_selector('%s > option' % selector)
        actual_values = []
        for option in options:
            actual_values.append(option.get_attribute('value'))
        self.assertEqual(values, actual_values)

    def has_css_class(self, selector, klass):
        """
        Returns True if the element identified by `selector` has the CSS class
        `klass`.
        """
        return (self.selenium.find_element_by_css_selector(selector)
                .get_attribute('class').find(klass) != -1)
