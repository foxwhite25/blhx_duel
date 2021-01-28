import os
import sqlite3
import ast

conn = sqlite3.connect('test.db')
c = conn.cursor()
r = c.execute('SELECT *, count(id) FROM namelist  GROUP by id ORDER BY COUNT(*) DESC').fetchall()
conn.commit()
for girl in r:
    text_file = open("test.txt", "a", encoding="utf-8")
    temp = ast.literal_eval(girl[1])
    if girl[0] < 2000 or girl[0] > 3000:
        temp[0], temp[1] = temp[1], temp[0]
    msg = str(girl[0]) + ":" + str(temp) + ",\n"
    text_file.write(msg)
