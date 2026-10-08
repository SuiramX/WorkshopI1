FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22-alpine AS runner

ENV NODE_ENV=production
WORKDIR /app

COPY --chown=node:node package.json server.js ./
COPY --chown=node:node --from=builder /app/dist ./dist

USER node
EXPOSE 3000
CMD ["npm", "start"]
