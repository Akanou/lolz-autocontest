from traceback_with_variables import Format, ColorSchemes, global_print_exc, printing_exc, LoggerAsFile
from bs4 import BeautifulSoup
import random
import string
from typing import Union
from urllib.parse import quote
from multiprocessing.pool import ThreadPool
import re
import time
import coloredlogs
import verboselogs
import sys
import os
from Crypto.Cipher import AES
import utils

import requests

import settings
import solvers

tg_token = settings.tg_token
tg_id = settings.tg_id

fmterr = Format(
    max_value_str_len=-1,
    color_scheme=ColorSchemes.common,
    max_exc_str_len=-1,
)
global_print_exc(fmt=fmterr)

import httpx

level_styles = {'debug': {'color': 8},
                'info': {},
                'warning': {'color': 11},
                'error': {'color': 'red'},
                'critical': {'bold': True, 'color': 'red'},

                'spam': {'color': 'green', 'faint': True},
                'verbose': {'color': 'blue'},
                'notice': {'color': 'magenta'},
                'success': {'bold': True, 'color': 'green'},
                }

logfmtstr = "%(asctime)s,%(msecs)03d %(name)s %(levelname)s %(message)s"
logfmt = coloredlogs.ColoredFormatter(logfmtstr, level_styles=level_styles)

pattern_csrf = re.compile(r'_csrfToken:\s*\"(.*)\",', re.MULTILINE)
pattern_df_id = re.compile(r'document\.cookie\s*=\s*"([^="]+)="\s*\+\s*toHex\(slowAES\.decrypt\(toNumbers\(\"([0-9a-f]{32})\"\)', re.MULTILINE)

class User:
    def makerequest(self,
                    method: str,
                    url,
                    checkforjs=False,
                    retries=1,
                    **kwargs) -> Union[httpx.Response, None]:
        for i in range(0, retries):
            try:
                resp = self.session.request(method, url, **kwargs)
                resp.raise_for_status()
            except httpx.TimeoutException as e:
                self.logger.warning("%s timeout", e.request.url)
                text = f"[WARN] {e.request.url} timeout"
                requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")
                self.changeproxy()
                time.sleep(settings.low_time)
            except httpx.ProxyError as e:
                self.logger.warning("%s proxy error (%s)", e.request.url, str(e))
                text = f"[WARN] {e.request.url} proxy error ({e})"                
                self.changeproxy()
                time.sleep(settings.low_time)
            except httpx.TransportError as e:
                self.logger.warning("%s TransportError (%s)", e.request.url, str(e))
                text = f"[WARN] {e.request.url} TransportError ({e})"
                self.changeproxy()
                time.sleep(settings.low_time)
            except httpx.HTTPStatusError as e:
                self.logger.warning("%s responded with %s status", e.request.url, e.response.status_code)
                text = f"[WARN] {e.request.url} responded with {e.response.status_code} status"
                time.sleep(settings.low_time)
            else:
                if checkforjs:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    if self.checkforjsandfix(soup):
                        self.logger.debug("%s had JS PoW", url)
                        text = f"[DEBUG] {url} had JS PoW"
        
                        continue  # we have js gayness

                return resp
        else:
            return None  # failed after x retries

    def checkforjsandfix(self, soup):
        noscript = soup.find("noscript")
        if not noscript:
            return False
        pstring = noscript.find("p")
        if not (pstring and pstring.string == "Oops! Please enable JavaScript and Cookies in your browser."):
            return False
        script = soup.find_all("script")
        if not script:
            return False
        if not (script[1].string.startswith('var _0xe1a2=["\\x70\\x75\\x73\\x68","\\x72\\x65\\x70\\x6C\\x61\\x63\\x65","\\x6C\\x65\\x6E\\x67\\x74\\x68","\\x63\\x6F\\x6E\\x73\\x74\\x72\\x75\\x63\\x74\\x6F\\x72","","\\x30","\\x74\\x6F\\x4C\\x6F\\x77\\x65\\x72\\x43\\x61\\x73\\x65"];function ')
                and script[0].get("src") == '/aes.js'):
            return False

        self.logger.verbose("lolz asks to complete aes task")
        text = f"lolz asks to complete aes task"

        match = pattern_df_id.search(script[1].string)
        cipher = AES.new(bytearray.fromhex("e9df592a0909bfa5fcff1ce7958e598b"), AES.MODE_CBC,
                         bytearray.fromhex("5d10aa76f4aed1bdf3dbb302e8863d52"))
        value = cipher.decrypt(bytearray.fromhex(match.group(2))).hex()
        self.logger.debug("PoW answer %s", str(value))
        text = f"PoW answer {value}"
        self.session.cookies.set(domain="." + settings.lolzdomain,
                                 name=match.group(1),
                                 value=value)
        return True  # should retry

    def changeproxy(self):
        if settings.proxy_type == 0:
            return

        newProxy = {}
        if settings.proxy_type == 1:
            randstr = ''.join(random.choices(string.ascii_lowercase, k=5))
            self.logger.verbose("changing proxy to %s", randstr)

            text = "changing proxy to {randstr}"
            requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")

            newProxy = {'all://': 'socks5://{}@localhost:9050'.format(randstr + ":" + self.username)}
        elif settings.proxy_type == 2:  # these are the moments i wish python had switch cases
            self.current_proxy_number += 1
            if self.current_proxy_number >= len(self.proxy_pool):
                self.current_proxy_number = 0
            proxy = self.proxy_pool[self.current_proxy_number]
            self.logger.verbose("changing proxy to %s index %d", proxy, self.current_proxy_number)
            newProxy = {'all://': proxy}
            pass
        elif settings.proxy_type == 3:  # TODO: implement global pool
            pass

        # hack to change proxies with httpx
        newSession = httpx.Client(http2=True, proxies=newProxy)
        newSession.headers = self.session.headers
        newSession.cookies = self.session.cookies
        self.session = newSession

    def solvegoogle(self, soup, url) -> Union[dict, None]:
        googletype = soup.find("input", attrs={"name": "googleCaptcha_type"})
        if googletype is None:
            raise RuntimeError("google captcha is missing. Something updated probably?")
        # self.logger.debug("google type: %s", googletype.attrs["value"])

        googlescript = soup.find("script")
        if googlescript is None:
            raise RuntimeError("google captcha script is missing. Something updated probably?")

        # v2sitekey = pattern_csrf.search(googlescript.string).group(1)
        # proxyprotocol, proxy = self.proxy_pool[self.current_proxy_number].split("://", maxsplit=1)
        params = {
            'key': settings.anti_captcha_key,
            'method': "userrecaptcha",
            'googlekey': settings.lolz_google_key,
            'pageurl': url,
            'userAgent': self.session.headers.get("User-Agent"),  # works without this too
            # 'proxy': proxy,
            # 'proxytype': proxyprotocol.upper(),  # not sure if upper is necessary.
            'json': 1
        }
        if settings.send_referral_to_creator:
            params["softguru"] = 109978

        submitresp = self.makerequest("GET", "http://api.captcha.guru/in.php", params=params)

        if submitresp is None:
            return None


        submit = submitresp.json()
        self.logger.debug(submit)
        if submit["status"] == 0:
            raise RuntimeError("submit was unsuccessful")  # TODO: handle this properly

        while True:
            time.sleep(5)
            resp = self.makerequest("GET",
                                    "http://api.captcha.guru/res.php",
                                    params={
                                        'key': settings.anti_captcha_key,
                                        'action': "get",
                                        'id': submit["request"],
                                        'json': 1
                                    })
            answer = resp.json()
            self.logger.debug(answer)
            if answer["status"] == 0 and answer["request"] == "CAPCHA_NOT_READY":
                continue
            elif answer["status"] == 1:
                return {
                    "googleCaptcha_type": "recaptcha",
                    "g-recaptcha-response": answer["request"],
                }
            else:
                raise RuntimeError("unknown state") # TODO: and this too


    def solvecontest(self, thrid) -> bool:  # return whether we were successful
        contestResp = self.makerequest("GET",
                                       settings.lolzUrl + "threads/" + str(thrid) + "/",
                                       retries=3,
                                       timeout=12.05,
                                       checkforjs=True)
        if contestResp is None:
            return False

        contestSoup = BeautifulSoup(contestResp.text, "html.parser")

        script = contestSoup.find("script", text=pattern_csrf)
        if script is None:
            self.logger.error("%s", str(contestSoup))
            text = f"[ERROR] no csrf token"
            requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")
            raise RuntimeError("no csrf token!")

        csrf = pattern_csrf.search(script.string).group(1)
        if not csrf:
            self.logger.critical("%s", str(contestSoup))
            text = f"[ERROR] csrf token is empty. likely bad cookies"
            requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")
            raise RuntimeError("csrf token is empty. likely bad cookies")
        self.logger.debug("csrf: %s", str(csrf))

        ContestCaptcha = contestSoup.find("div", class_="ContestCaptcha")
        if ContestCaptcha is None:
            self.logger.warning("Couldn't get ContestCaptcha. Lag or contest is over?")
            text = f"[INFO] Couldn't get ContestCaptcha. Lag or contest is over?"
            return False

        divcaptcha = ContestCaptcha.find("div", class_="captchaBlock")
        if divcaptcha is None:
            self.logger.warning("Couldn't get captchaBlock. Lag or contest is over?")
            text = f"[INFO] Couldn't get captchaBlock. Lag or contest is over?"
            return False

        captchatypeobj = divcaptcha.find("input", attrs={"name": "captcha_type"})

        if captchatypeobj is None:
            self.logger.warning("captcha_type not found. adding to blacklist...")
            text = f"[INFO] Captcha_type not found. adding to blacklist..."
            requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")
            self.blacklist.add(thrid)
            return False

        captchaType = captchatypeobj.get("value")
        if captchaType != "AnswerCaptcha":
            text = f"[INFO] Captcha type changed. bailing out"
            requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")
            raise RuntimeError("Captcha type changed. bailing out")

        participateParams = self.solver.solve(divcaptcha)
        if participateParams is None:
            return False

        googleParams = self.solvegoogle(ContestCaptcha, settings.lolzUrl + "threads/" + str(thrid) + "/")
        if googleParams is None:
            text = f"[INFO] google captcha response empty"
            requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")
            self.logger.warning("google captcha response empty")
            return False

        participateParams.update(googleParams)

        self.logger.info("waiting for participation...")
        response = self.participate(str(thrid), csrf, participateParams)
        if response is None:
            return False

        if "error" in response and response["error"][0] == 'Вы не можете участвовать в своём розыгрыше.':
            self.blacklist.add(thrid)

        if "_redirectStatus" in response and response["_redirectStatus"] == 'ok':
            self.logger.debug("%s", str(response))
            return True
        else:
            self.solver.onFailure(response)
            self.logger.error("didn't participate: %s", str(response))
            text = f"Не удалось принять участие в https://lolz.guru/threads/{thrid}/"
            requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")
            return False

    def solvepage(self) -> bool:
        found_contest = False
        contestListResp = self.makerequest("GET",
                                           settings.lolzUrl + "forums/contests/",
                                           timeout=12.05,
                                           retries=3,
                                           checkforjs=True)
        if contestListResp is None:
            return False

        contestlistsoup = BeautifulSoup(contestListResp.text, "html.parser")

        contestList = contestlistsoup.find("div", class_="discussionListItems")
        if contestList is None:
            self.logger.critical("%s", str(contestlistsoup))
            raise RuntimeError("couldn't find discussionListItems.")

        threadsList = []

        stickyThreads = contestList.find("div", class_="stickyThreads")
        if stickyThreads:
            threadsList.extend(stickyThreads.findChildren(recursive=False))

        latestThreads = contestList.find("div", class_="latestThreads")
        if latestThreads:
            threadsList.extend(latestThreads.findChildren(recursive=False))

        if len(threadsList) == 0:
            return False
        # TODO: make threadsList a list of threadids instead of html objects
        # also remove all blacklisted threadids before we get to this point
        self.logger.notice("detected %d contests", len(threadsList))
        
        total = 0
        
        for contestDiv in threadsList:                
            thrid = int(contestDiv.get('id').split('-')[1])

            if thrid in self.blacklist or thrid in settings.ExpireBlacklist:
                continue

            if not self.solver.onBeforeRequest(thrid):
                continue

            found_contest = True
            contestMoney = contestDiv.find("div", class_="discussionListItem--Wrapper") \
                .find("span", class_="prefix general moneyContestWithValue").contents[0]
            contestName = contestDiv.find("div", class_="discussionListItem--Wrapper") \
                .find("a", class_="listBlock main PreviewTooltip") \
                .find("h3", class_="title").find("span", class_="spanTitle").contents[0]

            self.logger.notice("participating in %s thread id %d", contestName, thrid)

            if self.solvecontest(thrid):
                total += 1
                self.logger.success("successfully participated in %s thread id %s", contestName, thrid)
                text = f"Успешно! Принято участие в https://lolz.guru/threads/{thrid}/ \nПриз: {contestMoney}₽ \n\nБаланс форума: {utils.getLolzGuruBalance()} \nБаланс сервиса: {utils.getCaptchaGuruBalance()}"
                requests.get(f"https://api.telegram.org/bot{tg_token}/sendMessage?chat_id={tg_id}&text={text}")

            time.sleep(settings.switch_time)
        return found_contest

    def work(self):
        with printing_exc(file_=LoggerAsFile(self.logger), fmt=fmterr):
            starttime = time.time()
            found_contest = 0

            self.logger.debug("work cookies %s", str(self.session.cookies))
            self.logger.debug("work headers %s", str(self.session.headers))
            ip = self.makerequest("GET", "https://httpbin.org/ip", timeout=12.05, retries=30)
            if ip:
                self.logger.notice("ip: %s", ip.json()["origin"])
            else:
                raise RuntimeError("Wasn't able to reach httpbin.org in 30 tries. Check your proxies and your internet connection")
            while True:
                cur_time = time.time()
                # remove old entries
                settings.ExpireBlacklist = {k: v for k, v in settings.ExpireBlacklist.items() if v > cur_time}
                self.logger.info("loop at %.2f seconds (blacklist size %d)", cur_time - starttime,
                                 len(settings.ExpireBlacklist))

                if self.solvepage():
                    found_contest = settings.found_count

                if found_contest > 0:
                    found_contest -= 1
                    time.sleep(settings.low_time)
                else:
                    time.sleep(settings.high_time)

    def __init__(self, parameters):
        self.session = httpx.Client(http2=True)
        self.username = parameters[0]

        self.logger = verboselogs.VerboseLogger(self.username)
        # self.logger.addHandler(consoleHandler)
        coloredlogs.install(fmt=logfmtstr, stream=sys.stdout, level_styles=level_styles,
                            milliseconds=True, level='DEBUG', logger=self.logger)
        self.logger.debug("user parameters %s", parameters)

        self.monitor_dims = (parameters[1]["monitor_size_x"], parameters[1]["monitor_size_y"])
        self.session.headers.update({"User-Agent": parameters[1]["User-Agent"]})
        for key, value in parameters[1]["cookies"].items():
            self.session.cookies.set(
                domain="." + settings.lolzdomain,
                name=key,
                value=value)

        if settings.proxy_type == 2:
            self.proxy_pool = parameters[1]["proxy_pool"]
            if len(self.proxy_pool) == 0:
                raise Exception("%s has empty proxy_pool" % self.username)

        self.blacklist = set()

        self.solver = solvers.SolverAnswers(self)

        # kinda a hack to loop trough proxies because python doesn't have static variables
        self.current_proxy_number = -1  # self.changeproxy adds one to this number
        self.changeproxy()  # set initital proxy
        self.session.cookies.set(domain=settings.lolzdomain, name='xf_viewedContestsHidden', value='1')
        self.session.cookies.set(domain=settings.lolzdomain, name='xf_feed_custom_order', value='post_date')
        self.session.cookies.set(domain=settings.lolzdomain, name='xf_logged_in', value='1')

    def participate(self, threadid: str, csrf: str, data: dict):
        # https://stackoverflow.com/questions/6005066/adding-dictionaries-together-python
        response = self.makerequest("POST", settings.lolzUrl + "threads/" + threadid + "/participate",
                                    data={**data, **{
                                        '_xfRequestUri': quote("/threads/" + threadid + "/"),
                                        '_xfNoRedirect': 1,
                                        '_xfToken': csrf,
                                        '_xfResponseType': "json",
                                    }}, timeout=12.05, retries=3, checkforjs=True)

        if response is None:
            return None

        return response.json()


def main():
    if not os.path.exists(settings.imagesDir):
        os.makedirs(settings.imagesDir)
    with ThreadPool(processes=len(settings.users)) as pool:
        userlist = [User(u) for u in list(settings.users.items())]
        pool.map(User.work, userlist)
        print("lul done?")


if __name__ == '__main__':
    main()
