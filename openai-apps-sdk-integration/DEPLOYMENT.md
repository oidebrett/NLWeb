# NLWeb MCP Server Deployment Guide

This guide explains how to host the NLWeb MCP server with its widget assets for production use.

## Architecture Overview

The NLWeb MCP server consists of two components:

1. **MCP Server** - Node.js server handling tool calls and widget metadata
2. **Widget Assets** - Static HTML, CSS, and JavaScript files for the UI

```
┌─────────────────┐
│   ChatGPT       │
│   (Client)      │
└────────┬────────┘
         │ HTTP/SSE
         │
┌────────▼────────┐       ┌──────────────────┐
│  MCP Server     │──────▶│  NLWeb Backend   │
│  (Port 8000)    │ HTTP  │  (API Server)    │
└────────┬────────┘       └──────────────────┘
         │
         │ References
         │
┌────────▼────────┐
│ Widget Assets   │
│ (CDN/Static)    │
│ - nlweb-list.js │
│ - nlweb-list.css│
└─────────────────┘
```

## Prerequisites

- Node.js 18+
- npm or pnpm
- A CDN or static file hosting service (e.g., CloudFlare, AWS S3, Azure Blob Storage)
- Domain or ngrok for public access (for ChatGPT integration)

## Part 1: Build the Widget Assets

### Step 1: Build the assets

```bash
cd /Users/linjli/source/MSFT/NLWeb/openai-apps-sdk-integration
npm run build
```

This creates versioned files in the `assets/` directory:
- `nlweb-list-{hash}.html`
- `nlweb-list-{hash}.js`
- `nlweb-list-{hash}.css`

### Step 2: Note the hash version

```bash
ls -la assets/ | grep nlweb-list
```

Example output:
```
nlweb-list-2d2b.css
nlweb-list-2d2b.html
nlweb-list-2d2b.js
```

The hash is `2d2b` in this example.

## Part 2: Host the Widget Assets

You have several options for hosting the static assets:

### Option A: Use a CDN (Recommended for Production)

#### CloudFlare R2 / Pages

1. **Upload assets:**
   ```bash
   # Install Wrangler CLI
   npm install -g wrangler
   
   # Login to CloudFlare
   wrangler login
   
   # Upload to R2
   wrangler r2 object put nlweb-assets/nlweb-list-2d2b.css --file=assets/nlweb-list-2d2b.css
   wrangler r2 object put nlweb-assets/nlweb-list-2d2b.js --file=assets/nlweb-list-2d2b.js
   ```

2. **Make assets public and note the URL:**
   ```
   https://your-bucket.r2.dev/nlweb-list-2d2b.css
   https://your-bucket.r2.dev/nlweb-list-2d2b.js
   ```

#### AWS S3 + CloudFront

1. **Upload to S3:**
   ```bash
   aws s3 cp assets/nlweb-list-2d2b.css s3://your-bucket/widgets/
   aws s3 cp assets/nlweb-list-2d2b.js s3://your-bucket/widgets/
   
   # Make public
   aws s3api put-object-acl --bucket your-bucket --key widgets/nlweb-list-2d2b.css --acl public-read
   aws s3api put-object-acl --bucket your-bucket --key widgets/nlweb-list-2d2b.js --acl public-read
   ```

2. **Configure CORS:**
   ```json
   {
     "CORSRules": [{
       "AllowedOrigins": ["*"],
       "AllowedMethods": ["GET"],
       "AllowedHeaders": ["*"]
     }]
   }
   ```

3. **Note your CloudFront URL:**
   ```
   https://d1234567890.cloudfront.net/widgets/nlweb-list-2d2b.css
   https://d1234567890.cloudfront.net/widgets/nlweb-list-2d2b.js
   ```

#### Azure Blob Storage + CDN

1. **Upload to Blob Storage:**
   ```bash
   az storage blob upload --account-name youraccount \
     --container-name widgets \
     --name nlweb-list-2d2b.css \
     --file assets/nlweb-list-2d2b.css \
     --content-type text/css
     
   az storage blob upload --account-name youraccount \
     --container-name widgets \
     --name nlweb-list-2d2b.js \
     --file assets/nlweb-list-2d2b.js \
     --content-type application/javascript
   ```

2. **Enable public access and CORS**

3. **Note your CDN endpoint:**
   ```
   https://youraccount.blob.core.windows.net/widgets/nlweb-list-2d2b.css
   https://youraccount.blob.core.windows.net/widgets/nlweb-list-2d2b.js
   ```

### Option B: Local Static Server (Development Only)

```bash
cd /Users/linjli/source/MSFT/NLWeb/openai-apps-sdk-integration
npm run serve
```

This serves assets at `http://localhost:4444` with CORS enabled.

**⚠️ Warning:** This only works for local testing. ChatGPT cannot access localhost.

## Part 3: Update the MCP Server Configuration

Edit `nlweb_server_node/src/server.ts`:

```typescript
const nlwebWidget: NLWebWidget = {
  id: "nlweb-list",
  title: "NLWeb Results",
  templateUri: "ui://widget/nlweb-list.html",
  invoking: "Searching NLWeb",
  invoked: "Found results",
  html: `
<div id="nlweb-list-root"></div>
<link rel="stylesheet" href="https://YOUR-CDN-URL/nlweb-list-2d2b.css">
<script type="module" src="https://YOUR-CDN-URL/nlweb-list-2d2b.js"></script>
  `.trim(),
  responseText: "Rendered a NLWeb result list!"
};
```

Replace `YOUR-CDN-URL` with your actual CDN URL.

**For local development:**
```typescript
<link rel="stylesheet" href="http://localhost:4444/nlweb-list-2d2b.css">
<script type="module" src="http://localhost:4444/nlweb-list-2d2b.js"></script>
```

## Part 4: Deploy the MCP Server

### Option A: Deploy to Azure App Service

1. **Install dependencies:**
   ```bash
   cd nlweb_server_node
   npm install
   ```

2. **Create Azure App Service:**
   ```bash
   az webapp create \
     --resource-group your-rg \
     --plan your-plan \
     --name nlweb-mcp-server \
     --runtime "NODE:18-lts"
   ```

3. **Configure environment variables:**
   ```bash
   az webapp config appsettings set \
     --resource-group your-rg \
     --name nlweb-mcp-server \
     --settings \
       NLWEB_APPSDK_BASE_URL=<TODO> \
       REQUEST_TIMEOUT="30000" \
       PORT="8000"
   ```

4. **Deploy:**
   ```bash
   # Build TypeScript
   npm run build  # If you add a build script
   
   # Deploy to Azure
   az webapp deployment source config-zip \
     --resource-group your-rg \
     --name nlweb-mcp-server \
     --src deploy.zip
   ```

5. **Note your server URL:**
   ```
   https://nlweb-mcp-server.azurewebsites.net/mcp
   ```

### Option B: Deploy to AWS (EC2 or App Runner)

1. **Create EC2 instance or use App Runner**

2. **Install Node.js and dependencies:**
   ```bash
   curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
   sudo apt-get install -y nodejs
   cd nlweb_server_node
   npm install
   ```

3. **Set environment variables:**
   ```bash
   export NLWEB_APPSDK_BASE_URL=<TODO>
   export REQUEST_TIMEOUT="30000"
   export PORT="8000"
   ```

4. **Run with PM2 (for production):**
   ```bash
   sudo npm install -g pm2
   pm2 start npm --name "nlweb-mcp" -- run start:http
   pm2 startup
   pm2 save
   ```

5. **Configure reverse proxy (nginx):**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location /mcp {
           proxy_pass http://localhost:8000/mcp;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
           
           # SSE specific settings
           proxy_buffering off;
           proxy_cache off;
       }
   }
   ```

### Option C: Use ngrok (Quick Testing)

1. **Start the server locally:**
   ```bash
   npm run start:http
   ```

2. **Expose with ngrok:**
   ```bash
   ngrok http 8000
   ```

3. **Note the ngrok URL:**
   ```
   https://abc123.ngrok-free.app/mcp
   ```

## Part 5: Configure in ChatGPT

1. **Enable Developer Mode** in ChatGPT
   - Go to Settings → Developer Mode
   - Enable it

2. **Add Connector:**
   - Go to Settings → Connectors
   - Click "Add Connector"
   - Enter your MCP endpoint URL:
     - Production: `https://your-domain.com/mcp`
     - ngrok: `https://abc123.ngrok-free.app/mcp`

3. **Test the integration:**
   - Start a new chat
   - Ask: "Search for spicy snacks on seriouseats.com"
   - The nlweb-list widget should render with results

## Testing Your Deployment

### Test 1: Check MCP Server is Running

```bash
# Should return SSE stream
curl -N https://your-domain.com/mcp
```

### Test 2: Run the Test Suite

```bash
# Update the URL in the test if needed
cd nlweb_server_node
npm run test
```

### Test 3: Verify Widget Assets Load

```bash
# Should return CSS
curl https://your-cdn-url/nlweb-list-2d2b.css

# Should return JavaScript
curl https://your-cdn-url/nlweb-list-2d2b.js
```

## Monitoring and Maintenance

### Check Server Logs

**Azure:**
```bash
az webapp log tail --name nlweb-mcp-server --resource-group your-rg
```

**PM2:**
```bash
pm2 logs nlweb-mcp
```

### Update Widget Assets

When you update the widget:

1. **Rebuild:**
   ```bash
   cd /Users/linjli/source/MSFT/NLWeb/openai-apps-sdk-integration
   npm run build
   ```

2. **Upload new assets** (with new hash)

3. **Update server code** with new URLs

4. **Redeploy server**

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `NLWEB_APPSDK_BASE_URL` | `<TODO>` | NLWeb APPSDK backend API URL |
| `REQUEST_TIMEOUT` | `30000` | Timeout for NLWeb requests (ms) |
| `PORT` | `8000` | Server port |

## Troubleshooting

### Widget Not Rendering

1. **Check CORS:** Ensure widget assets allow cross-origin requests
2. **Check URLs:** Verify CSS/JS URLs are accessible
3. **Check Browser Console:** Look for loading errors
4. **Verify Hash:** Make sure the hash in URLs matches built files

### Server Connection Issues

1. **Check Firewall:** Ensure port 8000 is open
2. **Check SSL:** Use HTTPS for production (ChatGPT requires it)
3. **Check Logs:** Review server logs for errors

### ChatGPT Not Calling Tool

1. **Verify Connector URL** is correct
2. **Check Server Logs** for incoming requests
3. **Test with Test Suite** to ensure server works

## Security Considerations

1. **HTTPS Required:** ChatGPT requires HTTPS endpoints
2. **CORS Configuration:** Only allow necessary origins
3. **Rate Limiting:** Implement rate limiting on your server
4. **API Keys:** If needed, add authentication to NLWeb backend calls
5. **Content Security Policy:** Configure CSP headers for widget assets

## Production Checklist

- [ ] Widget assets uploaded to CDN with CORS enabled
- [ ] Server deployed with HTTPS
- [ ] Environment variables configured
- [ ] Server URLs updated in code
- [ ] Test suite passes
- [ ] ChatGPT connector configured
- [ ] Monitoring/logging enabled
- [ ] Backup/disaster recovery plan
- [ ] Documentation updated

## Support

For issues or questions:
- Check logs first
- Run test suite: `npm run test`
- Review this documentation
- Check NLWeb backend status
