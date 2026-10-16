#!/data/data/com.termux/files/usr/bin/bash
# اسکریپت نصب خودکار ربات کلان‌شهر روی ترموکس
# اجرا: bash install.sh

set -e

echo "🏙️  نصب ربات کلان‌شهر روی ترموکس شروع شد..."
echo ""

echo "📦 آپدیت پکیج‌های ترموکس..."
pkg update -y && pkg upgrade -y

echo "🐍 نصب پایتون و ابزارهای لازم..."
pkg install -y python git

echo "📚 نصب کتابخانه‌های پایتون..."
# نکته: تو ترموکس جدید pip خودش با pkg مدیریت میشه و آپگریدش دستی ممنوعه،
# برای همین این مرحله رو رد می‌کنیم و مستقیم میریم سراغ نصب پکیج‌ها.
pip install -r requirements.txt --break-system-packages || pip install -r requirements.txt

# ساخت فایل .env در صورت نبودن
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  فایل .env ساخته شد. لطفاً بازش کن و BOT_TOKEN و OWNER_ID رو تنظیم کن:"
    echo "    nano .env"
    echo ""
fi

BOT_DIR="$(pwd)"

# اضافه کردن دستور میانبر S Kalan به bashrc (اگه نبود میسازیمش)
BASHRC="$HOME/.bashrc"
touch "$BASHRC"

if ! grep -q "# KALANSHAHR_BOT_SHORTCUT" "$BASHRC" 2>/dev/null; then
    cat >> "$BASHRC" << EOF

# KALANSHAHR_BOT_SHORTCUT
S() {
    if [ "\$1" == "Kalan" ] || [ "\$1" == "kalan" ]; then
        cd "$BOT_DIR" && python bot.py
    else
        command S "\$@" 2>/dev/null || echo "دستور نامعتبر. برای اجرای بات بنویس: S Kalan"
    fi
}
EOF
    echo "✅ دستور میانبر 'S Kalan' اضافه شد!"
fi

echo ""
echo "🎉 نصب تموم شد!"
echo ""
echo "مراحل بعدی:"
echo "  1) اگه هنوز توکن رو نذاشتی: nano .env"
echo "  2) این دستور رو بزن: source ~/.bashrc"
echo "  3) بنویس: S Kalan"
echo ""
