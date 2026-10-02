# ใช้ Nginx Alpine ซึ่งมีขนาดเล็กและเสิร์ฟไฟล์ HTML ได้รวดเร็ว
FROM nginx:alpine

# คัดลอกไฟล์ HTML/CSS/JS ทั้งหมดในโฟลเดอร์ frontend ไปยังไดเรกทอรีของ Nginx
COPY . /usr/share/nginx/html

# เปิดพอร์ต 80
EXPOSE 80