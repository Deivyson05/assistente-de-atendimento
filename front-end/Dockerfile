FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* e embutida no JavaScript no momento do build, nao em runtime.
# E o navegador (na maquina do usuario) que chama o backend, entao aqui vai o
# endereco publico do backend, e nao o nome do servico dentro da rede do Docker.
ARG NEXT_PUBLIC_BACKENDAPI=http://localhost:8000
ENV NEXT_PUBLIC_BACKENDAPI=$NEXT_PUBLIC_BACKENDAPI

RUN npm run build


FROM node:22-alpine

WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.ts ./next.config.ts

EXPOSE 3000

CMD ["npm", "start"]
