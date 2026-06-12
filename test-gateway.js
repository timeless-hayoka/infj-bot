import { createOpenAI } from '@ai-sdk/openai';
import { streamText } from 'ai';
import dotenv from 'dotenv';

// Load local environment variables pulled by Vercel CLI
dotenv.config({ path: '.env.local' });

const oidcToken = process.env.VERCEL_OIDC_TOKEN;

if (!oidcToken) {
  console.error("Error: VERCEL_OIDC_TOKEN is missing in .env.local.");
  console.error("Please run `vercel env pull` again to refresh your tokens.");
  process.exit(1);
}

console.log("Configuring OpenAI provider via Vercel AI Gateway...");

// Create the OpenAI provider instance pointing to Vercel AI Gateway
const openai = createOpenAI({
  baseURL: 'https://ai-gateway.vercel.sh/v1',
  apiKey: oidcToken,
});

try {
  console.log("Sending streaming request using model 'openai/gpt-5.5'...");
  const result = await streamText({
    model: openai('gpt-5.5'),
    prompt: 'Write a brief, punchy summary of how Vercel AI Gateway enables keyless token routing.',
  });

  console.log("\n=== Response Stream ===");
  for await (const textPart of result.textStream) {
    process.stdout.write(textPart);
  }
  console.log("\n=======================\n");
} catch (error) {
  console.error("Streaming failed:", error);
  process.exit(1);
}
