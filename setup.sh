#!/bin/bash

set -e

echo "🚀 ドアロックくん セットアップを開始します..."

# 1. 仮想環境の作成とライブラリのインストール
echo "📦 Python 仮想環境を作成し、依存ライブラリをインストールしています..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 2. .env ファイルの準備
if [ ! -f .env ]; then
    echo "📝 .env ファイルが見つからないため、テンプレートを作成します..."
    cat << 'EOF' > .env
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
EOF
    echo "⚠️ .env ファイルを作成しました。適切なAPIキー等を入力してください。"
else
    echo "✅ .env ファイルは既に存在します。"
fi

# 3. systemd サービスファイルの生成と登録
SERVICE_NAME="switchbot.service"
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)

echo "⚙️ systemd サービス (${SERVICE_NAME}) を設定しています..."

sudo bash -c "cat << EOF > /etc/systemd/system/${SERVICE_NAME}
[Unit]
Description=SwitchBot LINE Bot Service
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CURRENT_DIR}
ExecStart=${CURRENT_DIR}/venv/bin/python3 ${CURRENT_DIR}/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF"

# 4. サービスの有効化と起動
echo "🔄 systemd をリロードし、サービスを起動しています..."
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

echo "✨ セットアップが正常に完了しました！"
echo "📊 動作状態の確認: sudo systemctl status ${SERVICE_NAME}"
