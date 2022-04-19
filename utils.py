import requests
from bs4 import BeautifulSoup
from settings import user_agent, cookie, anti_captcha_key

headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'accept-encoding': 'gzip, deflate, br',
    'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,da;q=0.6',
    'cache-control': 'max-age=0',
    'cookie': cookie,
    'referer': 'https://lolz.guru/',
    'sec-ch-ua-mobile': '?0',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': user_agent
        }

response = requests.get('https://lolz.guru/market/', headers=headers)
soup = BeautifulSoup(response.text, 'lxml')

def getLolzGuruBalance():   
   response = requests.get(f'https://lolz.guru/market/user/5236640/payments', headers=headers)
   soup = BeautifulSoup(response.text, 'lxml')
   bal = soup.find('span', class_='balanceValue').text
   try:
       balHold = soup.find('span', class_='balanceNumber muted').text.replace("\n","").replace("	","")
   except:
       balHold = 0
   return f"{bal}₽ / Замороженные: {balHold}₽"

def getCaptchaGuruBalance():
    response = requests.get(f'http://api.captcha.guru/res.php?action=getbalance&key={anti_captcha_key}')
    soup = BeautifulSoup(response.text, 'lxml')
    bal = soup.find('body').text
    return f"{bal}₽"