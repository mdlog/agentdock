# AgentDock frontend — build the CRA bundle, serve it as static files.
#
# Create React App bakes every REACT_APP_* value at BUILD time, so the backend
# URL and chain config are build args, not runtime env. Rebuild to change them.
FROM node:20-slim AS build
WORKDIR /app

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 600000

COPY . .

ARG REACT_APP_BACKEND_URL
ARG REACT_APP_BSC_RPC_URL
ARG REACT_APP_BSC_MAINNET_RPC_URL
ARG REACT_APP_BINANCE_WALLET_URL
ARG REACT_APP_ERC8004_MAINNET_REGISTRY
ARG REACT_APP_ERC8004_TESTNET_REGISTRY
ARG REACT_APP_8004SCAN_URL
RUN yarn build

# Serve the static build. nginx config falls back to index.html so client-side
# routes (/onchain, /hire/..., /tasks/...) resolve on refresh.
FROM nginx:1.27-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
