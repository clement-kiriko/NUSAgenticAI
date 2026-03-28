FROM node:20-alpine AS builder

WORKDIR /app

ARG VITE_API_BASE=
ARG VITE_WS_BASE=
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_WS_BASE=${VITE_WS_BASE}

COPY TripBuddy/frontend/package.json TripBuddy/frontend/package-lock.json ./
RUN npm ci

COPY TripBuddy/frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime

ENV API_UPSTREAM=http://backend:8000

# Place config as a template (not in /etc/nginx/templates/ — we do substitution ourselves)
COPY TripBuddy/frontend/nginx.conf /etc/nginx/conf.d/default.conf.template
COPY TripBuddy/frontend/docker-entrypoint.sh /start-nginx.sh
RUN chmod +x /start-nginx.sh
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["/start-nginx.sh"]
