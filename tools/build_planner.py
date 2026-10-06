# -*- coding: utf-8 -*-
"""planner/template.html 에 blueprint/web_data.json 을 넣어 planner/index.html 생성."""
import json, sys
tpl = open("planner/template.html", encoding="utf-8").read()
data = json.load(open("blueprint/web_data.json", encoding="utf-8"))
sim = json.load(open("blueprint/raid_sim_v3.json", encoding="utf-8"))
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
sim_blob = json.dumps(sim, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
open("planner/index.html", "w", encoding="utf-8").write(tpl.replace("__DATA__", blob).replace("__SIM__", sim_blob))
print("planner/index.html", len(tpl) + len(blob), "bytes")
