# 🚀 دليل رفع وتشغيل النظام على PythonAnywhere
## Academic Management System - PythonAnywhere Deployment Guide

---

## 📦 محتويات حزمة الرفع (Export Package)
تم تجهيز جميع الملفات المطلوبة للرفع تلقائياً:
- `academic_system_pythonanywhere.zip` (الملف المضغوط الجاهز للرفع)
- `requirements.txt` (قائمة الحزم البرمجية المطلوبة)
- `pythonanywhere_wsgi.py` (ملف إعداد خادم WSGI)
- `instance/football_academic.db` (قاعدة البيانات الحالية مع الحسابات والبيانات)

---

## 📋 الخطوات خطوة بخطوة (Step-by-Step)

### الخطوة 1: رفع الملفات إلى PythonAnywhere (Upload Files)
1. سجل دخول إلى حسابك على [PythonAnywhere](https://www.pythonanywhere.com/).
2. توجه إلى تبويب **Files**.
3. تحت قسم **Upload a file**، اختر ملف `academic_system_pythonanywhere.zip` واضغط **Upload**.
4. افتح تبويب **Consoles** وافتح شاشة **Bash Console**، ثم نفذ الأوامر التالية لفك الضغط في مجلد المشروع:
   ```bash
   mkdir -p Academic-System-Clean
   unzip academic_system_pythonanywhere.zip -d Academic-System-Clean
   cd Academic-System-Clean
   ```

---

### الخطوة 2: إنشاء البيئة الافتراضية وتثبيت المكتبات (Virtual Environment)
في نفس شاشة الـ **Bash Console**، قم بإنشاء بيئة عمل افتراضية وتثبيت المتطلبات:

```bash
# إنشاء بيئة افتراضية باسم venv باستخدام Python 3.11
python3.11 -m venv venv

# تفعيل البيئة
source venv/bin/activate

# ترقية pip وتثبيت متطلبات النظام
pip install --upgrade pip
pip install -r requirements.txt
```

---

### الخطوة 3: إنشاء تطبيق الويب (Create Web App)
1. توجه إلى تبويب **Web** في لوحة تحكم PythonAnywhere.
2. اضغط على **Add a new web app**.
3. اختر اسم النطاق الافتراضي (e.g. `yourusername.pythonanywhere.com`) ثم اضغط **Next**.
4. اختر **Manual configuration** (لا تختر Flask التلقائي لأننا سنستخدم بيئتنا الخاصة).
5. اختر إصدار **Python 3.11** واضغط **Next**.

---

### الخطوة 4: ضبط مسارات تطبيق الويب (Virtualenv & Code Paths)
في صفحة **Web**:
1. في قسم **Code**:
   - **Source code**: `/home/YOUR_USERNAME/Academic-System-Clean`
   - **Working directory**: `/home/YOUR_USERNAME/Academic-System-Clean`
2. في قسم **Virtualenv**:
   - اضغط على المسار واكتب: `/home/YOUR_USERNAME/Academic-System-Clean/venv`
3. في قسم **Static files**:
   - أضف مسار الملفات الثابتة:
     - **URL**: `/static/`
     - **Directory**: `/home/YOUR_USERNAME/Academic-System-Clean/static`

*(ملاحظة: استبدل `YOUR_USERNAME` باسم المستخدم الخاص بك في PythonAnywhere)*

---

### الخطوة 5: تعديل ملف الـ WSGI (WSGI Configuration)
1. في تبويب **Web**، في قسم **Code**، اضغط على رابط:
   `WSGI configuration file` (مثال: `/var/www/yourusername_pythonanywhere_com_wsgi.py`).
2. احذف كل المحتوى الموجود داخل الملف وضع بدلاً منه الكود التالي:

```python
import os
import sys

# ضع اسم المستخدم الخاص بك هنا
USERNAME = 'YOUR_USERNAME'
PROJECT_DIR = f'/home/{USERNAME}/Academic-System-Clean'

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    os.chdir(PROJECT_DIR)
except Exception:
    pass

from app import app as application, initialize_app

# تهيئة قاعدة البيانات والتحديثات عند الإقلاع
initialize_app()
```
3. اضغط **Save** في أعلى الصفحة.

---

### الخطوة 6: إعادة تشغيل الخادم والدخول (Reload & Access)
1. ارجع إلى تبويب **Web**.
2. اضغط على الزر الأخضر الكبير **Reload yourusername.pythonanywhere.com**.
3. افتح رابط موقعك: `https://yourusername.pythonanywhere.com`

---

## 🔑 بيانات الدخول الافتراضية
- **اسم المستخدم (Username):** `abbas96sport`
- **كلمة المرور (Password):** `11234511`
