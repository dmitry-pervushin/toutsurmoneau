#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
# Based on the great job done by ooio (https://github.com/ooii/pySuez)
#
"""
This is the module to interact with toutsurmoneau.fr
"""
import argparse
import asyncio
import datetime
import getpass
import logging
import pytz
import re

import aiohttp


class SuezError(Exception):
    """
    Exceptions that could be raised by SuezClient
    """


class SuezClient():
    """
    SuezClient is a representation of the client view

    You need to instantiate this object to interact with the suez websize
    """

    API_ENDPOINT_LOGIN = '/mon-compte-en-ligne/je-me-connecte'
    API_ENDPOINT_CONSUMPTION = '/mon-compte-en-ligne/historique-de-consommation-tr'
    API_ENDPOINT_DATA = '/mon-compte-en-ligne/statJData'
    API_ENDPOINT_HISTORY = '/mon-compte-en-ligne/statMData'
    _providers = {
        'toutsurmoneau' : 'https://www.toutsurmoneau.fr',
        'Eau Olivet'    : 'https://www.eau-olivet.fr'
    }
    EPSILON = 0.000001

    def __init__(self, username, password, counter_id, provider=None, timeout=None, logger=None):
        """
        Initialize the client interface.
        Required parameters are userrname, password and counter_id
        provider is optional, if None then toutsurmoneau.fr will be used
        timeout is well, the timeout - None is safe in most cases
        logger will be used to log some debugging data, default None is OK
        """
        self._username = username
        self._password = password
        self._counter_id = counter_id
        self._token = ''
        self._session = None
        self._timeout = timeout
        self._provider = provider or 'toutsurmoneau'
        self._logger = logger or logging.getLogger(__name__)

        self.success = False
        self.uptodate = False
        self.attribution = None
        self.last = None
        self.this_month = None
        self.prev_month = None
        self.history = None
        self.this_year_overall = None
        self.last_year_overall = None
        self.highest_monthly = None

    def _url(self, endpoint = ''):
        """ Use custom base URL if needed """
        return self._providers[self._provider] + endpoint

    @classmethod
    def providers(cls):
        """ Return list of known providers """
        return list(cls._providers.keys())

    def _get_token_1(self, content):
        phrase = re.compile('csrf_token(.*)')
        result = phrase.search(content)
        if result is None:
            self._logger.info("cannot get token using method I")
            return None
        self._logger.info("Looks like I get token use method I")
        return result.group(1)

    def _get_token_2(self, content):
        phrase = re.compile('csrfToken\\\\u0022\\\\u003A\\\\u0022([^,]+)\\\\u0022,\\\\u0022')
        result = phrase.search(content)
        if result is None:
            self._logger.info("cannot get token using method II")
            return None
        self._logger.info("Looks like I get token use method II")
        return result.group(1).encode().decode('unicode_escape')

    def _cookies(self):
        cookies = self._session.cookie_jar.filter_cookies(self._url())
        self._logger.debug(f"{cookies=}")
        return cookies

    async def _get_token(self):
        """
        Get the CSRF token
        """
        response = await self._fetch_url('', self.API_ENDPOINT_LOGIN)

        decoded_content = await response.text(encoding='utf-8')
        self._token = self._get_token_1(decoded_content) or self._get_token_2(decoded_content)
        if self._token is None:
            raise SuezError("Can't get token.")

        self._logger.debug(f"Found token = {self._token}")
        return {
            '_username': self._username,
            '_password': self._password,
            '_csrf_token': self._token,
            'signin[username]': self._username,
            'signin[password]': None,
            'tsme_user_login[_username]': self._username,
            'tsme_user_login[_password]': self._password
        }

    def _rq(self, url, data = None, method = None, **kwargs):
        verb = method
        if data is not None:
            verb = 'post'
        if verb is None:
            verb = 'get'
        return self._session.request(verb, url, data=data, **kwargs)

    async def _get_cookie(self):
        """
        Connect and get the cookie
        """
        data = await self._get_token()
        try:
            async with self._rq(self._url(self.API_ENDPOINT_LOGIN),
                                data=data,
                                allow_redirects=False,
                                timeout=self._timeout) as rq:
               await rq.text(encoding='utf-8')
        except OSError as exc:
            raise SuezError("Can not submit login form.") from exc

        if not 'eZSESSID' in self._cookies():
            raise SuezError("Login error: Please check your username/password.")

        return True

    def _fetch_url(self, url_tail, endpoint):
        url = self._url(endpoint)
        if url_tail:
             url = url + "/" + url_tail
        self._logger.info(f"Fetching {url=}")
        return self._rq(url, timeout=self._timeout)

    async def _fetch_data_url(self, url_tail, endpoint=None):
        """
        Fetch the data from base_url/endpoint/url_tail using GET

        if endpoint is NULL, self.API_ENDPOINT_DATA is used
        """
        ep = endpoint
        if ep is None:
            ep = self.API_ENDPOINT_DATA
        data = await self._fetch_url(url_tail, ep)
        json = await data.json()
        self._logger.debug(f"Loaded {json=}")
        if len(json) and str(json[0]) == 'ERR':
            raise SuezError(str(json[1]) if len(json) > 1 else "Unknown error")
        return json

    async def _fetch_consumption(self):
        #
        # the counter_id can be found in some URLs on the page, like:
        #
        pattern = re.compile('exporter-consommation/month/([0-9]+)')
        data = await self._fetch_url('', self.API_ENDPOINT_CONSUMPTION)
        counter_id = pattern.search(await data.text(encoding='utf-8'))
        return counter_id.group(1)

    def ensure_type(self, candidate, typelist):
        """
        make sure that each item of candidate has type from typelist
        """
        for (value, expected_type) in zip(candidate, typelist):
            if not isinstance(value, expected_type):
                raise SuezError(f"{value} was expected to be {expected_type}")

    async def _fetch_last_known(self, today):
        now = today
        _year_month = ""
        last_known_good = None
        candidate = None
        count = 0
        while (last_known_good is None or last_known_good < 0.0001) and count < 60:
            if _year_month != f"{now.year}/{now.month}":
                 _year_month = f"{now.year}/{now.month}"
                 candidate = await self._fetch_data_url(f"{_year_month}/{self._counter_id}")
            if candidate is not None:
                 date_txt, delta, total = candidate[now.day - 1]
                 last_known_good = total
                 self.ensure_type([total], [(int, float)])
            now = now - datetime.timedelta(days=1)
            count = count + 1
        return last_known_good

    async def _fetch_data(self):
        """
        Fetch latest data from Suez
        """

        self.success = False
        self.uptodate = False

        await self._get_cookie()

        if self._counter_id is None:
            self._counter_id = await self._fetch_consumption()

        # get the current time in France: data on the website is updated in this timezone

        now = datetime.datetime.now(pytz.timezone('Europe/Paris'))
        try:
            self.last_known = await self._fetch_last_known(now)
        except SuezError as exc:
            self.last_known = 0

        yesterday = now - datetime.timedelta(days=1)
        first_this_month = now.replace(day=1)
        prev_month = first_this_month - datetime.timedelta(days=1)

        try:
            today_json = await self._fetch_data_url(f"{now.year}/{now.month}/{self._counter_id}")
        except SuezError as exc:
            today_json = {}
            self._logger.warning(f"Fetching todaty's data: {exc}")
        if yesterday.month != now.month:
            yesterday_json = await self._fetch_data_url(f"{yesterday.year}/{yesterday.month}/{self._counter_id}")
        else:
            yesterday_json = today_json
        prev_month_json = await self._fetch_data_url(f"{prev_month.year}/{prev_month.month}/{self._counter_id}")
        history_json = await self._fetch_data_url(f'{self._counter_id}', endpoint=self.API_ENDPOINT_HISTORY)

        try:
            self.last = yesterday_json[yesterday.day - 1][1:]
            self.ensure_type(self.last, [(int, float), (int, float)])
        except Exception as exc:
            raise SuezError("Cannot read yesterday data") from exc

        try:
            self.this_month = {j[0]: j[1:] for j in today_json}
            for (month, consumption) in self.this_month.items():
                self.ensure_type([month], [str])
                self.ensure_type(consumption, [(int, float), (int, float)])
        except Exception as exc:
            raise SuezError("Cannot read this month data") from exc

        try:
            self.prev_month = {j[0]: j[1:] for j in prev_month_json}
            for (month, consumption) in self.prev_month.items():
                self.ensure_type([month], [str])
                self.ensure_type(consumption, [(int, float), (int, float)])
        except Exception as exc:
            raise SuezError("Cannot read previous month data") from exc

        try:
            self.highest_monthly = history_json[-1]
            self.ensure_type([self.highest_monthly], [(int, float)])
        except Exception as exc:
            raise SuezError("Cannot convert highest_monthly") from exc

        try:
            self.last_year_overall = history_json[-2]
            self.ensure_type([self.last_year_overall], [(int, float)])
        except Exception as exc:
            raise SuezError("Cannot convert last_year_overall") from exc

        try:
            self.this_year_overall = history_json[-3]
            self.ensure_type([self.this_year_overall], [(int, float)])
        except Exception as exc:
            raise SuezError("Cannot convert this_year_overall") from exc

        try:
            self.history = {j[3]: j[1:3] for j in history_json[:-3]}
            for (month, consumption) in self.history.items():
                self.ensure_type([month], [str])
                self.ensure_type(consumption, [(int, float), (int, float)])
        except Exception as exc:
            raise SuezError("Cannot convert history") from exc

        self.success = True
        self.uptodate = self.last[0] > self.EPSILON

        self.attribution = f"Data provided by {self._provider} ({self._url('')})"

    async def _check_credentials(self):
        data = await self._get_token()
        try:
            response = await self._session.post(self._url(self.API_ENDPOINT_LOGIN),
                                                data=data,
                                                allow_redirects=False,
                                                timeout=self._timeout)
        except OSError as exc:
            raise SuezError("Can not submit login form.") from exc
        self._logger.debug(f"Got cookies {response.cookies}")

        return 'eZSESSID' in response.cookies

    async def update_async(self):
        """Asynchronous update"""
        async with self.session() as self._session:
            return await self._fetch_data()

    async def check_credentials_async(self):
        """Asynchronous check_credential"""
        async with self.session() as self._session:
            return await self._check_credentials()

    def update(self):
        """Synchronous update"""
        return asyncio.run(self.update_async())

    def check_credentials(self):
        """Asynchronous check_credential"""
        return asyncio.run(self.check_credentials_async())

    async def _trace(self, session, context, params):
        self._logger.debug(f'{params}')

    def session(self):
        trace = aiohttp.TraceConfig()
        trace.on_request_start.append(self._trace)
        trace.on_request_end.append(self._trace)
        trace.on_request_exception.append(self._trace)
        return aiohttp.ClientSession(trace_configs = [trace])


def __main():
    """
    Main function
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--username',
                        default=None,
                        help='Suez username')
    parser.add_argument('-p', '--password',
                        default=None,
                        help='Password')
    parser.add_argument('-c', '--counter_id',
                        default=None,
                        help='Counter Id')
    parser.add_argument('-P', '--provider',
                        default=None,
                        help='Provider name')
    parser.add_argument('-v', '--verbose',
                        default=0, action='count',
                        help='Verbosity level')

    parser.add_argument('command',
                        choices=['show', 'providers', 'check'],
                        default='show',
                        nargs='?',
                        help='Command to execute. Default is "show"')

    args = parser.parse_args()
    need_args = args.command not in ['providers']

    if args.username is None and need_args:
        args.username = input('Username  : ')
    if args.password is None and need_args:
        args.password = getpass.getpass('Password  : ')

    logger = None
    if args.verbose > 0:
        logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%H:%M:%S', level = max(40 - args.verbose  * 10, 0))
        logger = logging.getLogger(__name__)

    suez = SuezClient(args.username, args.password, args.counter_id, args.provider, logger=logger)

    if args.command == 'providers':
        print(f'Available providers are: {suez.providers()}')
        return

    if args.command == 'check':
        print("Checking credentials....")
        print("Pass!" if suez.check_credentials() else "Error")
        return

    if args.command == 'show':
        print("Getting updates....")
        suez.update()
        if suez.success:
            print(f'{suez.last_known=}')
            print(f'{suez.last=}')
            print(f'{suez.this_month=}')
            print(f'{suez.prev_month=}')
            print(f'{suez.history=}')
            print(f'{suez.this_year_overall=}')
            print(f'{suez.last_year_overall=}')
            print(f'{suez.highest_monthly=}')
        return


if __name__ == '__main__':
    __main()
