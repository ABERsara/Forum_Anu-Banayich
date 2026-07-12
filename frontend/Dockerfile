FROM node:22-slim

WORKDIR /app

# Install dependencies first so this layer stays cached across builds
# unless package.json/package-lock.json actually change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 4200

CMD ["npm", "start", "--", "--host", "0.0.0.0"]
