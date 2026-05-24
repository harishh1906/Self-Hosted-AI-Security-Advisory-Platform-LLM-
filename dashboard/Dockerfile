# ── Virtue-AI Dashboard — Production Dockerfile ──
# Multi-stage build: Node for build, Nginx for serving

# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies first (cached layer)
COPY package.json package-lock.json ./
RUN npm ci --production=false

# Copy source and build
COPY . .
RUN npm run build

# Stage 2: Production Nginx
FROM nginx:1.27-alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config for SPA routing + reverse proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget --spider -q http://127.0.0.1:3000/health-check || exit 1

EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
