# -*- coding: utf-8 -*-
# подставляет данные в шаблон: tpl.html + records.json + api/attrib.json -> dashboard-influence.html
t=open('tpl.html',encoding='utf-8').read()
t=t.replace('__DATA__',open('records.json',encoding='utf-8').read().strip())
t=t.replace('__ATTR__',open('api/attrib.json',encoding='utf-8').read().strip())
open('dashboard-influence.html','w',encoding='utf-8').write(t)
print('собрано, байт:',len(t))
