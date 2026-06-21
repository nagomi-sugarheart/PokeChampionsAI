import requests
import json
import time

# 1. まず全ポケモンのリスト（URLの塊）を取得
print("ポケモンリストを取得中...")
response = requests.get("https://pokeapi.co/api/v2/pokemon?limit=1025") # 現時点の全一般ポケモン数に調整
pokemon_list = response.json()["results"]

pokemon_db = {}

# 2. 各ポケモンの詳細URLに自動でアクセスして、技とデータを引っこ抜く
for i, p in enumerate(pokemon_list):
    name = p["name"]
    url = p["url"]
    
    print(f"[{i+1}/{len(pokemon_list)}] {name} のデータを取得中...")
    
    try:
        res = requests.get(url)
        detail = res.json()
        
        # 必要なデータだけを抽出して軽量化
        pokemon_db[name] = {
            "id": detail["id"],
            "types": [t["type"]["name"] for t in detail["types"]],
            "stats": {s["stat"]["name"]: s["base_stat"] for s in detail["stats"]},
            # ★ここで「覚える技の名前」だけをリストにして抽出！
            "moves": [m["move"]["name"] for m in detail["moves"]] 
        }
    except Exception as e:
        print(f"エラー発生 ({name}): {e}")
    
    # サーバーに負荷をかけないよう、少し待つ（これ大事！）
    time.sleep(0.5)

# 3. ローカルにJSONとして保存
with open("pokemon_moves_db.json", "w", encoding="utf-8") as f:
    json.dump(pokemon_db, f, indent=2, ensure_ascii=False)

print("完了しました！")