# ドアロックくん (SwitchBot LINE Bot)

LINE Bot と SwitchBot スマートロックを連携させ、トーク画面や専用QRコードから安全に鍵の解錠・施錠を行うシステムです。Raspberry Pi 4 などの Linux サーバー上で常駐させる想定です。

このリポジトリは、構築メモ（ラズパイ4でのスマート家電とバックアップ）の最終仕様を、**秘密情報を含まない公開用コード**として整理したものです。トークンやユーザーIDは `.env` のみに置き、Git には入れません。

## 主な機能

- LINE から「開けて」「閉めて」で鍵を操作
- 初回利用は QR / 合言葉 → 管理者の LINE で承認（永久 / 2時間 / 日時指定 / 拒否）
- 30分ごとに変わるワンタイムQR（`/qr`）
- 無効キー3回連続で15分間ロックアウト
- Web ログ画面（`/logs`）
- 「室温」「温度」でハブ／温湿度計の値を表示
- 顔認証パッドや手動操作を SwitchBot Webhook で検知し、管理者へ通知
- プロジェクト一式の tar バックアップ（`scripts/backup.sh`）

## 必要なもの

- Python 3.9 以上
- Raspberry Pi / Linux
- SwitchBot Smart Lock とハブ（ハブミニ / ハブ2 など）
- LINE Messaging API（Messaging API チャネル）
- 公開 HTTPS URL（ngrok の固定ドメイン推奨）

## かんたんセットアップ（Raspberry Pi）

```bash
git clone https://github.com/<your-username>/door-locker-for-rpi4.git
cd door-locker-for-rpi4
chmod +x setup.sh scripts/backup.sh
./setup.sh
nano .env
```

`.env` に API キーを書いたら再起動します。

```bash
sudo systemctl restart switchbot.service
```

デバイス ID が分からない場合:

```bash
./venv/bin/python3 list_devices.py
```

顔認証パッドや手動操作の通知を使う場合（`.env` の `WEBHOOK_URL` または `PUBLIC_BASE_URL` を設定してから一度だけ）:

```bash
./venv/bin/python3 register_webhook.py
```

`statusCode` が `100` なら成功です。

手動起動（動作確認用）:

```bash
source venv/bin/activate
python3 app.py
```

## 環境変数（`.env`）

`.env.example` をコピーして埋めます。

| 変数 | 内容 |
| --- | --- |
| `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_CHANNEL_SECRET` | LINE Developers のチャネル情報 |
| `BOT_BASIC_ID` | Bot のベーシック ID（例: `@xxxx`）。QR の LINE 起動 URL に使う |
| `ADMIN_USER_ID` | 管理者の LINE ユーザー ID。Bot に「マイID」と送ると取得できる |
| `SECRET_DASHBOARD_KEY` | `/logs?key=` の閲覧キー |
| `DASHBOARD_USER` / `DASHBOARD_PASSWORD` | `/logs` の Basic 認証（パスワード空なら無効） |
| `TOTP_SECRET` | 動的 QR の種 |
| `SWITCHBOT_TOKEN` / `SWITCHBOT_SECRET` | SwitchBot Open API |
| `DEVICE_ID` | スマートロックの deviceId |
| `HUB_DEVICE_ID` | 温湿度を取るハブまたはメーターの deviceId |
| `AUTH_SECRET_KEY` | 固定の合言葉（任意。QR は `KEY_...` が主） |
| `PUBLIC_BASE_URL` / `WEBHOOK_URL` | HTTPS の公開先 |

## LINE Developers と ngrok

1. Flask は `5000` 番で待ち受けます。
2. ngrok で公開します。**トンネル全体に Basic 認証をかけないでください。** LINE の `/callback` が 401 になり、Webhook 検証に失敗します。画面保護はアプリ側の `/logs` で行います。

```bash
ngrok http 5000 --url=YOUR_STATIC_DOMAIN.ngrok-free.dev
```

常駐例は `systemd/ngrok.service` を参照し、ユーザー名・パス・ドメインを書き換えてから `/etc/systemd/system/` に配置します。

3. LINE Developers の Webhook URL を次に設定し、「Webhookの利用」を ON、検証を実行します。

```text
https://YOUR_STATIC_DOMAIN.ngrok-free.dev/callback
```

4. リッチメニューを使う場合は Official Account Manager で、テキスト送信「開けて」「閉めて」「予約」「マイID」を割り当てます。

## LINE コマンド

| コマンド | 説明 |
| --- | --- |
| 開けて | 鍵を開錠します（初回は管理者承認が必要です）。 |
| 閉めて | 鍵を施錠します。 |
| 室温 / 温度 / 湿度 / 環境 | ハブまたは温湿度計の値を表示します。 |
| 予約 | 指定時刻に自動開錠する予約を設定します。 |
| 予約取消 | 開錠予約をキャンセルします。 |
| マイID | 自分の LINE ユーザー ID を表示します。 |
| ヘルプ | 利用ガイドを表示します。 |
| リセット | 自分の承認状態を解除します。 |

## Web 画面

- QR: `https://<公開ドメイン>/qr`
- ログ: `https://<公開ドメイン>/logs?key=<SECRET_DASHBOARD_KEY>`（加えて Basic 認証）

承認済みユーザー一覧はメモリ上のみです。サービス再起動で消えます。

## バックアップ

プロジェクト（`.env` 含む、`venv` とログは除外）を tar.gz にします。

```bash
chmod +x scripts/backup.sh
./scripts/backup.sh
```

保存先はデフォルトで `backups/` です。USB などに出す場合:

```bash
BACKUP_DIR=/mnt/usb/door-locker ./scripts/backup.sh
```

毎日 3 時に取る例（crontab）:

```cron
0 3 * * * /home/pi/door-locker-for-rpi4/scripts/backup.sh
```

SD カード全体のイメージバックアップ（別途、電源オフまたは別媒体推奨）は Raspberry Pi 公式の SD カードコピーや `dd` 等を使ってください。本スクリプトはアプリ設定の退避用です。

## トラブルシュート

| 症状 | 確認 |
| --- | --- |
| LINE が無反応、`/callback` がログに出ない | Webhook URL が `/callback` で終わっているか。ngrok に Basic 認証が付いていないか |
| Webhook 検証が 401 | ngrok の `--basic-auth` を外す |
| 起動するが鍵が動かない | `list_devices.py` で `DEVICE_ID` が合っているか。SwitchBot トークン |
| `dotenv` がない | `venv` 内の Python で実行する（`./venv/bin/python3 ...`） |
| ログ確認 | `journalctl -u switchbot.service -f` |

## セキュリティ

- `.env` と実トークンは公開リポジトリに含めない（`.gitignore` 済み）
- 資料やチャットに残った古いトークンは、公開前に LINE / SwitchBot 側で再発行することを推奨します
- `/qr` は玄関ディスプレイ向けに認証なしです。不要ならファイアウォールやローカル LAN のみで公開してください

## ファイル構成

```text
app.py                 # LINE Bot + Flask
register_webhook.py    # SwitchBot イベント通知の登録
list_devices.py        # デバイス ID 一覧
setup.sh               # venv / systemd 一括セットアップ
scripts/backup.sh      # 設定バックアップ
templates/logs.html    # ログ画面
systemd/               # 常駐ユニットのひな形
.env.example           # 環境変数のテンプレート
```
