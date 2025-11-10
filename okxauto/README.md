## Environment Variables (.env support)

You can store your OKX API credentials in a `.env` file in the project root or set them in your environment. The following variables are supported:

```
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_API_PASSPHRASE=your_api_passphrase
```

The CLI will automatically load these from `.env` if present (using `github.com/joho/godotenv`). 