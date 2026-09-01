# 🔑 ドアロックくん (SwitchBot LINE Bot)

LINE BotとSwitchBotスマートロックを連携させ、LINEのトーク画面や専用QRコードから安全に鍵の解錠・施錠を行うスマートホームシステムです。

---

## 🌟 主な機能

* **LINEからの鍵操作:** 「開けて」「閉めて」のメッセージで鍵を簡単操作。
* **柔軟な管理者承認:** 初回利用申請に対し、管理者のLINEから「永久承認」「2時間限定」「日時指定」でアクセス権限を付与。
* **動的ワンタイムQRコード認証:** 30分ごとに自動切り替わるQRコード（`/qr`）を使った安全な利用申請。
* **自動セキュリティロックアウト:** 無効なキーを3回連続入力したユーザーを15分間自動ブロック。
* **Webダッシュボード:** リアルタイムログ確認（`/logs`）およびQRコードのブラウザ表示。
* **環境モニタリング:** 「室温」「温度」メッセージでハブミニからリアルタイムの温度・湿度を取得・表示。
* **物理操作検知:** 顔認証パッドや手動ツマミ操作を検知し、管理者へのリアルタイムPush通知とログ記録を実行。

---

## 🛠 動作環境

* Linux サーバー / Raspberry Pi
* Python 3.9 以上
* SwitchBot Smart Lock & ハブミニ
* ngrok (固定ドメイン推奨)
* LINE Messaging API アカウント

---

## 🚀 簡単セットアップ手順

本リポジトリには、仮想環境の作成からパッケージ依存関係の解決、`.env` テンプレートの作成、`systemd` サービス化までを自動で行うセットアップスクリプトを用意しています。

### 1. リポジトリのクローン

```bash
sudo git clone [https://github.com/your-username/door-lock-kun.git](https://github.com/your-username/door-lock-kun.git)
cd door-lock-kun
```

### 2. 実行権限の付与とスクリプトの実行

```bash
sudo chmod +x setup.sh
./setup.sh
```

### 3. 環境変数（.env）の設定

生成された .env ファイルに、実際の各種APIキーやIDを設定します。

```bash
sudo nano .env
```

```bash
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_CHANNEL_SECRET=your_line_channel_secret
BOT_BASIC_ID=@your_bot_basic_id

ADMIN_USER_ID=your_admin_line_user_id
SECRET_DASHBOARD_KEY=your_dashboard_access_key
TOTP_SECRET=your_totp_secret_key

SWITCHBOT_TOKEN=your_switchbot_api_token
SWITCHBOT_SECRET=your_switchbot_api_secret
DEVICE_ID=your_switchbot_lock_device_id
HUB_DEVICE_ID=your_switchbot_hub_device_id

AUTH_SECRET_KEY=your_static_secret_key
```

###4. SwitchBot Webhook の登録 & サービスの再起動
顔認証パッドや手動操作の検知イベントを受信するため、一度だけWebhook登録を行います。

```bash
# Webhook登録
./venv/bin/python3 register_webhook.py
```
# 設定反映のためサービスを再起動
```bash
sudo systemctl restart switchbot.service
```

| コマンド | 説明 |
| :--- | :--- |
| **開けて** | 鍵を開錠します（初回利用時は管理者の承認が必要です）。 |
| **閉めて** | 鍵を施錠します。 |
| **室温** / **温度** | ハブミニから現在の室温・湿度を取得して表示します。 |
| **予約** | 指定した時刻に自動で鍵を開ける予約を設定します。 |
| **予約取消** | 設定した自動開錠予約をキャンセルします。 |
| **マイID** | 自身のLINEユーザーIDを表示・コピーできます。 |
| **ヘルプ** | システムの利用ガイドメッセージを表示します。 |
| **リセット** | 自身のユーザー登録状態（認証権限）を初期化します。 |
