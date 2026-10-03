# دستیار جواب ایمیل (Gmail + Claude)

این برنامه ایمیل‌های جدید جیمیل را می‌خواند، با Claude برایشان پیش‌نویس جواب می‌نویسد و آن‌ها را در یک صف تسک نگه می‌دارد. تو هر تسک را باز می‌کنی، در صورت نیاز ویرایش یا بازنویسی می‌کنی و با «تأیید و ارسال» جواب در همان رشته‌ی ایمیل فرستاده می‌شود. هیچ ایمیلی بدون تأیید تو ارسال نمی‌شود.

## ساختار پروژه

```
app/
  config.py        تنظیمات از متغیرهای محیطی
  db.py            مدل‌های دیتابیس (تسک‌ها و توکن گوگل)
  gmail_client.py  اتصال OAuth، خواندن ایمیل، ارسال reply
  ai.py            نوشتن پیش‌نویس با Claude
  worker.py        فرایند پس‌زمینه که هر چند دقیقه صندوق را بررسی می‌کند
  main.py          وب‌اپ FastAPI (داشبورد، تأیید، ارسال)
  templates/       صفحه‌های داشبورد
Dockerfile, docker-compose.yml, Caddyfile
```

## ۱. ساخت OAuth Client در Google Cloud

1. به https://console.cloud.google.com برو و یک پروژه‌ی جدید بساز.
2. در APIs & Services → Library، سرویس **Gmail API** را فعال کن.
3. در OAuth consent screen نوع کاربر را External بگذار (یا اگر Google Workspace داری Internal)، و ایمیل خودت را در بخش Test users اضافه کن.
4. در Credentials → Create credentials → OAuth client ID، نوع **Web application** را انتخاب کن و این Redirect URI ها را اضافه کن:
   - `http://localhost:8000/auth/callback` برای تست روی کامپیوتر خودت
   - `https://mail.example.com/auth/callback` با دامنه‌ی واقعی خودت برای سرور
5. Client ID و Client Secret را در فایل `.env` بگذار.

نکته‌ی مهم: اگر اپ گوگل در حالت Testing و نوع External باشد، گوگل توکن را هر ۷ روز باطل می‌کند و باید از داشبورد دوباره «اتصال جیمیل» را بزنی. برای رفع کامل این محدودیت دو راه داری: استفاده از حساب Google Workspace با نوع Internal، یا Publish کردن اپ (که برای دسترسی جیمیل نیاز به بررسی گوگل دارد).

## ۲. اجرا روی کامپیوتر خودت

```bash
cp .env.example .env
# مقادیر را پر کن و BASE_URL را بگذار: http://localhost:8000
docker compose up --build web worker
```

بعد http://localhost:8000 را باز کن، با رمز داشبورد وارد شو و «اتصال جیمیل» را بزن.

## ۳. استقرار روی AWS (EC2)

1. یک EC2 با Ubuntu بساز (t3.small کافی است). در Security Group پورت‌های 22، 80 و 443 را باز کن.
2. یک Elastic IP به آن وصل کن تا آی‌پی ثابت بماند، و رکورد A دامنه‌ات (مثلاً `mail.example.com`) را به آن آی‌پی بده.
3. روی سرور Docker نصب کن:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER   # بعدش یک‌بار logout/login کن
   ```
4. پروژه را روی سرور کپی کن (با git یا scp)، فایل `.env` را بساز و `BASE_URL=https://mail.example.com` بگذار.
5. در `Caddyfile` دامنه‌ی خودت را جایگزین کن. Caddy خودش گواهی HTTPS می‌گیرد.
6. اجرا:
   ```bash
   docker compose up -d --build
   docker compose logs -f worker
   ```

به خاطر `restart: always`، اگر برنامه کرش کند یا سرور ریستارت شود، همه‌چیز خودکار دوباره بالا می‌آید.

## تنظیمات مفید در `.env`

`GMAIL_QUERY` تعیین می‌کند کدام ایمیل‌ها جواب بگیرند. پیش‌فرض فقط ایمیل‌های خوانده‌نشده‌ی دو روز اخیر را بدون تبلیغات و شبکه‌های اجتماعی برمی‌دارد. اگر ایمیل‌ها را معمولاً قبل از برنامه در جیمیل باز می‌کنی، `is:unread` را حذف کن. با `label:` هم می‌توانی فقط یک برچسب خاص را هدف بگیری.

`REPLY_STYLE`، `OWNER_NAME` و `EMAIL_SIGNATURE` لحن و امضای جواب‌ها را تعیین می‌کنند. Claude همیشه به زبان خود فرستنده جواب می‌دهد و جاهایی که اطلاعات ندارد را با کروشه مثل `[زمان جلسه]` علامت می‌زند تا خودت پر کنی.

ایمیل‌های خبرنامه، no-reply و ایمیل‌هایی که خودت فرستاده‌ای خودکار نادیده گرفته می‌شوند.

## امنیت

کلیدها را هرگز در git نگذار (`.env` در `.gitignore` است). برای `SECRET_KEY` و `DASHBOARD_PASSWORD` مقدار طولانی و تصادفی بگذار. در محیط جدی‌تر بهتر است کلیدها را در AWS Secrets Manager نگه داری و از RDS به جای SQLite استفاده کنی؛ فقط کافی است `DATABASE_URL` را عوض کنی.

## ایده‌های نسخه‌ی بعد

اعلان در تلگرام یا ایمیل وقتی تسک جدید می‌آید، اولویت‌بندی ایمیل‌ها با هوش مصنوعی، و یادگیری لحن از جواب‌هایی که قبلاً ویرایش کرده‌ای.
