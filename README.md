# supermarket.io

Jogo 3D multiplayer feito com three.js, Flask e Socket.IO: segurança de supermercado com câmeras, sensores, semáforo, caixa, placas e fotos compartilhadas pelo celular.

## Como rodar

```bash
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:5000 no computador.

- **Criar sala**: o anfitrião cria a sala e recebe um código de 5 letras.
- **Entrar como segurança**: os outros jogadores digitam o código e entram no lobby (só até a partida começar).
- **Celular do segurança**: abra http://IP-DO-COMPUTADOR:5000/celular no celular, digite o código e compartilhe fotos com a equipe.

Os bancos ficam em `data/` (caixa.db e placas.db), criados automaticamente.
