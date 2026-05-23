FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# Bumped via docker-compose `FORGE_UI_BUILD_REV` so `docker compose build` picks up UI changes
# even when dependency layers are cached.
ARG FORGE_UI_BUILD_REV=0
ENV NEXT_PUBLIC_FORGE_UI_BUILD_REV=${FORGE_UI_BUILD_REV}
RUN echo "FORGE_UI_BUILD_REV=${FORGE_UI_BUILD_REV}"
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# Used only at build time for next.config rewrites (local `next dev`).
ARG BFF_INTERNAL_URL=http://bff:8000
ENV BFF_INTERNAL_URL=$BFF_INTERNAL_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
