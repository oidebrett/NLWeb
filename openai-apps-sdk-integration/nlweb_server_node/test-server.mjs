#!/usr/bin/env node

/**
 * Test script for SSE-based MCP server
 * 
 * Usage:
 *   node test-server.mjs [port]
 * 
 * Example:
 *   node test-server.mjs 8000
 */

import fetch from 'node-fetch';
import EventSourcePkg from 'eventsource';
const EventSource = EventSourcePkg.default || EventSourcePkg;

const PORT = process.argv[2] || 8000;
const BASE_URL = `http://localhost:${PORT}`;
const SSE_URL = `${BASE_URL}/mcp`;
const MESSAGE_URL = `${BASE_URL}/mcp/messages`;

console.log('🧪 Testing NLWeb MCP Server (SSE)');
console.log(`📡 Connecting to: ${SSE_URL}\n`);

let sessionId = null;
let testsPassed = 0;
let testsFailed = 0;

// Connect to SSE stream
const eventSource = new EventSource(SSE_URL);

eventSource.onopen = () => {
  console.log('✅ SSE connection opened');
  console.log('⏳ Waiting for session ID from endpoint event...\n');
};

eventSource.onerror = (error) => {
  console.error('❌ SSE connection error:', error.message || error);
  testsFailed++;
  eventSource.close();
  process.exit(1);
};

// Listen for the 'endpoint' event which contains the session ID
eventSource.addEventListener('endpoint', async (event) => {
  try {
    console.log('📨 Received endpoint event');
    console.log('   Data:', event.data);
    
    // The endpoint event data is the URL path: /mcp/messages?sessionId=...
    // Extract the sessionId from the query parameter
    const url = new URL(event.data, BASE_URL);
    sessionId = url.searchParams.get('sessionId');
    
    if (sessionId) {
      console.log(`✅ Session ID: ${sessionId}\n`);
      testsPassed++;
      
      // Start running tests
      await runTests();
    } else {
      console.error('❌ No sessionId found in endpoint data');
      testsFailed++;
      eventSource.close();
      process.exit(1);
    }
  } catch (error) {
    console.error('❌ Error parsing endpoint event:', error.message);
    console.log('   Data:', event.data);
    testsFailed++;
    eventSource.close();
    process.exit(1);
  }
});

eventSource.onmessage = async (event) => {
  try {
    console.log('📨 Received message:', event.data.substring(0, 100));
    const data = JSON.parse(event.data);
    
    if (data.method === 'notifications/initialized') {
      console.log('✅ Server initialized notification received');
      testsPassed++;
    }
  } catch (error) {
    console.log('📝 SSE data (non-JSON):', event.data);
  }
};

async function runTests() {
  console.log('🚀 Starting MCP Protocol Tests\n');
  
  try {
    // Test 1: List Tools
    await testListTools();
    
    // Test 2: List Resources
    await testListResources();
    
    // Test 3: Read Resource
    await testReadResource();
    
    // Test 4: Call Tool with query
    await testCallTool('spicy snacks', 'seriouseats');
    
    // Print summary
    console.log('\n' + '='.repeat(50));
    console.log('📊 Test Summary');
    console.log('='.repeat(50));
    console.log(`✅ Passed: ${testsPassed}`);
    console.log(`❌ Failed: ${testsFailed}`);
    console.log('='.repeat(50) + '\n');
    
    // Close connection
    eventSource.close();
    process.exit(testsFailed > 0 ? 1 : 0);
  } catch (error) {
    console.error('❌ Test suite failed:', error.message);
    testsFailed++;
    eventSource.close();
    process.exit(1);
  }
}

const pendingRequests = new Map();

// Listen for message responses via SSE
eventSource.addEventListener('message', async (event) => {
  try {
    const data = JSON.parse(event.data);
    
    if (data.id && pendingRequests.has(data.id)) {
      const { resolve } = pendingRequests.get(data.id);
      pendingRequests.delete(data.id);
      resolve(data);
    }
  } catch (error) {
    console.log('📝 SSE message data:', event.data.substring(0, 200));
  }
});

async function sendRequest(method, params = {}) {
  const requestId = Date.now();
  const request = {
    jsonrpc: '2.0',
    id: requestId,
    method,
    params
  };
  
  const url = `${MESSAGE_URL}?sessionId=${sessionId}`;
  
  // Create a promise that will be resolved when we receive the SSE response
  const responsePromise = new Promise((resolve, reject) => {
    pendingRequests.set(requestId, { resolve, reject });
    
    // Timeout after 10 seconds
    setTimeout(() => {
      if (pendingRequests.has(requestId)) {
        pendingRequests.delete(requestId);
        reject(new Error('Request timeout'));
      }
    }, 10000);
  });
  
  // Send the request
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  
  // For SSE transport, we expect 202 Accepted
  if (response.status !== 202) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  
  // Wait for the actual response via SSE
  return await responsePromise;
}

async function testListTools() {
  console.log('🧪 Test 1: List Tools');
  console.log('   Method: tools/list');
  
  try {
    const response = await sendRequest('tools/list');
    
    if (response.result && response.result.tools) {
      console.log(`   ✅ Found ${response.result.tools.length} tool(s)`);
      response.result.tools.forEach((tool, i) => {
        console.log(`      ${i + 1}. ${tool.name} - ${tool.description || tool.title}`);
      });
      testsPassed++;
    } else {
      console.log('   ❌ No tools found in response');
      testsFailed++;
    }
  } catch (error) {
    console.log(`   ❌ Error: ${error.message}`);
    testsFailed++;
  }
  console.log();
}

async function testListResources() {
  console.log('🧪 Test 2: List Resources');
  console.log('   Method: resources/list');
  
  try {
    const response = await sendRequest('resources/list');
    
    if (response.result && response.result.resources) {
      console.log(`   ✅ Found ${response.result.resources.length} resource(s)`);
      response.result.resources.forEach((resource, i) => {
        console.log(`      ${i + 1}. ${resource.name} (${resource.mimeType})`);
        console.log(`         URI: ${resource.uri}`);
      });
      testsPassed++;
    } else {
      console.log('   ❌ No resources found in response');
      testsFailed++;
    }
  } catch (error) {
    console.log(`   ❌ Error: ${error.message}`);
    testsFailed++;
  }
  console.log();
}

async function testReadResource() {
  console.log('🧪 Test 3: Read Resource');
  console.log('   Method: resources/read');
  console.log('   URI: ui://widget/nlweb-list.html');
  
  try {
    const response = await sendRequest('resources/read', {
      uri: 'ui://widget/nlweb-list.html'
    });
    
    if (response.result && response.result.contents) {
      const content = response.result.contents[0];
      console.log(`   ✅ Resource read successfully`);
      console.log(`      MIME Type: ${content.mimeType}`);
      console.log(`      Text length: ${content.text?.length || 0} chars`);
      if (content.text) {
        const preview = content.text.substring(0, 100);
        console.log(`      Preview: ${preview}...`);
      }
      testsPassed++;
    } else {
      console.log('   ❌ No content in response');
      testsFailed++;
    }
  } catch (error) {
    console.log(`   ❌ Error: ${error.message}`);
    testsFailed++;
  }
  console.log();
}

async function testCallTool(query, site) {
  console.log('🧪 Test 4: Call Tool');
  console.log('   Method: tools/call');
  console.log(`   Tool: nlweb-list`);
  console.log(`   Query: "${query}"`);
  if (site) {
    console.log(`   Site: ${site}`);
  }
  
  try {
    const args = {
      query: query,
      mode: 'list'
    };
    
    if (site) {
      args.site = site;
    }
    
    const response = await sendRequest('tools/call', {
      name: 'nlweb-list',
      arguments: args
    });
    
    if (response.result) {
      console.log('   ✅ Tool executed successfully');
      
      // Check content
      if (response.result.content) {
        console.log(`      Content: ${response.result.content.length} item(s)`);
        response.result.content.forEach((item, i) => {
          if (item.type === 'text') {
            console.log(`         ${i + 1}. ${item.text.substring(0, 80)}...`);
          }
        });
      }
      
      // Check structured content
      if (response.result.structuredContent) {
        const sc = response.result.structuredContent;
        console.log(`      Structured Content:`);
        console.log(`         Query: ${sc.query || 'N/A'}`);
        console.log(`         Results: ${sc.results?.length || 0} item(s)`);
        console.log(`         Messages: ${sc.messages?.length || 0} message(s)`);
        
        if (sc.results && sc.results.length > 0) {
          console.log(`      First Result:`);
          const first = sc.results[0];
          console.log(`         Type: ${first['@type'] || 'Unknown'}`);
          console.log(`         Name: ${first.name || 'N/A'}`);
          console.log(`         Score: ${first.score || 'N/A'}`);
        }
      }
      
      // Check widget metadata
      if (response.result._meta) {
        console.log(`      Widget Metadata:`);
        const meta = response.result._meta;
        if (meta['openai/outputTemplate']) {
          console.log(`         Template: ${meta['openai/outputTemplate']}`);
        }
        if (meta['openai/toolInvocation/invoking']) {
          console.log(`         Invoking: ${meta['openai/toolInvocation/invoking']}`);
        }
        if (meta['openai/toolInvocation/invoked']) {
          console.log(`         Invoked: ${meta['openai/toolInvocation/invoked']}`);
        }
      }
      
      testsPassed++;
    } else if (response.error) {
      console.log(`   ⚠️  Tool returned error: ${response.error.message}`);
      testsFailed++;
    } else {
      console.log('   ❌ No result in response');
      testsFailed++;
    }
  } catch (error) {
    console.log(`   ❌ Error: ${error.message}`);
    testsFailed++;
  }
  console.log();
}

// Handle process termination
process.on('SIGINT', () => {
  console.log('\n\n⚠️  Test interrupted by user');
  eventSource.close();
  process.exit(1);
});

// Timeout after 30 seconds
setTimeout(() => {
  console.error('\n❌ Test timeout after 30 seconds');
  eventSource.close();
  process.exit(1);
}, 60000);
