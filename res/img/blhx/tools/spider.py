import requests
from lxml import etree
from urllib import request
import os
import sqlite3

os.chdir(r'输入你的目录')
url = 'https://wiki.biligame.com/blhx/%E8%88%B0%E5%A8%98%E5%9B%BE%E9%89%B4'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 '
                  'Safari/537.36'}
fo = open("test.txt", "a")
conn = sqlite3.connect('test.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS namelist
       (ID INT PRIMARY KEY     NOT NULL,
       list           TEXT    NOT NULL);''')
conn.commit()


def get_urls(url):
    resp = requests.get(url, headers=headers)
    text = resp.text
    html = etree.HTML(text)
    detail_urls = []
    for urls in html.xpath(
            '//div[@style="position:relative;display:inline-block;overflow:hidden;border-radius:5px"]/a/@href'):
        detail_urls.append(urls)
    return detail_urls


def get_data(url):
    stl = 0
    detail_url = 'https://wiki.biligame.com/' + str(url)
    resp = requests.get(detail_url, headers=headers)
    text = resp.text
    html = etree.HTML(text)
    name = html.xpath('//*[@id="mw-content-text"]/div/div[6]/div[1]/table[1]/tbody/tr[1]/td//text()')
    id = html.xpath('//*[@id="PNN"]/text()')
    jpg = html.xpath('//*[@id="mw-content-text"]/div/div[6]/div[1]/table[1]/tbody/tr[2]/td[1]/img/@src')
    level = html.xpath('//*[@id="mw-content-text"]/div/div[6]/div[1]/table[1]/tbody/tr[3]/td[2]/text()')
    try:
        stlevel = level[0]
        stid = id[0]
        stlevel = stlevel[:-1]
        stid = stid.replace("Collab", "2")
        stid = stid.replace("Plan", "3")
        stid = stid.replace("META", "4")
        if int(stid) < 2000:
            stid = "1" + stid
        del name[1::2]
        print(stid + str(name))
        c = conn.cursor()
        c.execute('INSERT INTO namelist (id,"list") VALUES (?,?)', (stid, str(name),), )
        conn.commit()
        if stlevel == "普通" or stlevel == "稀有":
            stl = 1
        if stlevel == "精锐":
            stl = 3
        if stlevel == "超稀有" or stlevel == "海上传奇" or stlevel == "最高方案" or stlevel == "决战方案":
            stl = 6
        realname = "icon_unit_" + str(stid) + str(stl) + "1" + ".png"
        request.urlretrieve(jpg[0], realname)  # 转换成图片
    except:
        pass


def main():
    detail_urls = get_urls(url)
    for each in detail_urls:
        get_data(each)


if __name__ == '__main__':
    main()
