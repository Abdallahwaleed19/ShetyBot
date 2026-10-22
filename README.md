# SehtyBot — بوت الإجازات المرضية

بوت Telegram لإنشاء تقارير الإجازات المرضية الرسمية وحفظها في قاعدة البيانات.

## المتطلبات
- Python 3.11+
- MySQL / MariaDB
- Cloudflare Tunnel (للـ HTTPS)

## التشغيل المحلي

```bash
pip install -r requirements.txt
cp .env.example .env
# عدّل .env بقيمك
python run_bot.py    # في terminal 1
python run_web.py    # في terminal 2
```

## النشر على السيرفر

```bash
bash setup.sh           # مرة واحدة فقط
bash install_services.sh  # مرة واحدة فقط
```

## تحديث الكود

```bash
bash update.sh
```
