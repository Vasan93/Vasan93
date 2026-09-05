FROM node:22-alpine

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-fund --no-audit

COPY frontend .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
