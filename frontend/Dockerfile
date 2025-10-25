# Используем Node 20 — совместим с Next.js 16
FROM node:20-alpine

WORKDIR /app

# Копируем только package.json для ускорения кеша
COPY package*.json ./

RUN npm install

# Копируем исходники
COPY . .

# Экспонируем порт Next.js
EXPOSE 3000

# По умолчанию — dev режим
CMD ["npm", "run", "dev"]
