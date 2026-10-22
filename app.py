"""Ponto de entrada: python app.py -> http://127.0.0.1:5001"""
from rotina import criar_app

app = criar_app()

if __name__ == "__main__":
    cfg = app.config["ROTINA"]
    app.run(host=cfg.get("host", "127.0.0.1"), port=int(cfg.get("porta", 5001)), debug=False)
