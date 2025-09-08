# Client Integration Guide

## Quick Start

### 1. Install Supabase Client

```bash
# JavaScript/TypeScript
npm install @supabase/supabase-js

# Python
pip install supabase

# Flutter
flutter pub add supabase_flutter
```

### 2. Initialize Client

```javascript
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_KEY
);
```

## Implementation Examples

### React/Next.js

```typescript
import { useState, useEffect } from 'react';
import { createClient } from '@supabase/supabase-js';

interface StreamingMessage {
  id: string;
  ai_id: string;
  content: string;
  is_complete: boolean;
}

export function useChatRoom(roomId: string, threadId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingMessages, setStreamingMessages] = useState<Map<string, StreamingMessage>>(new Map());
  
  useEffect(() => {
    const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
    
    // Subscribe to room updates
    const channel = supabase.channel(`room-${roomId}-thread-${threadId}`)
      // Listen for completed messages
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'messages',
        filter: `room_id=eq.${roomId},thread_id=eq.${threadId}`
      }, (payload) => {
        setMessages(prev => [...prev, payload.new]);
      })
      // Listen for streaming messages
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'streaming_messages',
        filter: `room_id=eq.${roomId},thread_id=eq.${threadId}`
      }, (payload) => {
        handleStreamingUpdate(payload);
      })
      .subscribe();
    
    return () => channel.unsubscribe();
  }, [roomId, threadId]);
  
  const sendMessage = async (content: string, aiId: string) => {
    // 1. Save user message
    const { data: userMessage } = await supabase
      .from('messages')
      .insert({
        room_id: roomId,
        thread_id: threadId,
        content: content,
        sender_type: 1,
        sender_id: userId
      })
      .select()
      .single();
    
    // 2. Request AI response
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        room_id: roomId,
        thread_id: threadId,
        ai_id: aiId,
        user_message_id: userMessage.id
      })
    });
    
    const { streaming_message_id } = await response.json();
    // Updates will come through subscription
  };
  
  const handleStreamingUpdate = (payload: any) => {
    const { eventType, new: data, old } = payload;
    
    setStreamingMessages(prev => {
      const next = new Map(prev);
      
      switch (eventType) {
        case 'INSERT':
          next.set(data.id, data);
          break;
        case 'UPDATE':
          if (data.is_complete) {
            next.delete(data.id);
          } else {
            next.set(data.id, data);
          }
          break;
        case 'DELETE':
          next.delete(old.id);
          break;
      }
      
      return next;
    });
  };
  
  return {
    messages,
    streamingMessages: Array.from(streamingMessages.values()),
    sendMessage
  };
}

// Usage in component
function ChatRoom({ roomId, threadId }) {
  const { messages, streamingMessages, sendMessage } = useChatRoom(roomId, threadId);
  
  return (
    <div className="chat-room">
      {messages.map(msg => (
        <Message key={msg.id} {...msg} />
      ))}
      
      {streamingMessages.map(streaming => (
        <div key={streaming.id} className="streaming-message">
          <div className="typing-indicator">AI is typing...</div>
          <div>{streaming.content}</div>
        </div>
      ))}
    </div>
  );
}
```

### Vue 3

```vue
<template>
  <div class="chat-room">
    <div v-for="msg in messages" :key="msg.id">
      {{ msg.content }}
    </div>
    
    <div v-for="stream in streamingMessages" :key="stream.id" class="streaming">
      <span class="typing">AI is typing...</span>
      <div>{{ stream.content }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { createClient } from '@supabase/supabase-js';

const props = defineProps<{
  roomId: string;
  threadId: string;
}>();

const messages = ref([]);
const streamingMessages = ref(new Map());
let channel;

onMounted(() => {
  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
  
  channel = supabase.channel(`room-${props.roomId}`)
    .on('postgres_changes', {
      event: '*',
      schema: 'public',
      table: 'streaming_messages',
      filter: `room_id=eq.${props.roomId},thread_id=eq.${props.threadId}`
    }, handleStreamingChange)
    .on('postgres_changes', {
      event: 'INSERT',
      schema: 'public',
      table: 'messages',
      filter: `room_id=eq.${props.roomId},thread_id=eq.${props.threadId}`
    }, (payload) => {
      messages.value.push(payload.new);
    })
    .subscribe();
});

const handleStreamingChange = (payload) => {
  const { eventType, new: data, old } = payload;
  
  switch (eventType) {
    case 'INSERT':
      streamingMessages.value.set(data.id, data);
      break;
    case 'UPDATE':
      if (data.is_complete) {
        streamingMessages.value.delete(data.id);
      } else {
        streamingMessages.value.set(data.id, data);
      }
      break;
    case 'DELETE':
      streamingMessages.value.delete(old.id);
      break;
  }
  
  // Trigger reactivity
  streamingMessages.value = new Map(streamingMessages.value);
};

onUnmounted(() => {
  channel?.unsubscribe();
});
</script>
```

### Vanilla JavaScript

```javascript
class ChatClient {
  constructor(roomId, threadId) {
    this.roomId = roomId;
    this.threadId = threadId;
    this.supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
    this.messages = [];
    this.streamingMessages = new Map();
    this.subscribe();
  }
  
  subscribe() {
    this.channel = this.supabase
      .channel(`room-${this.roomId}`)
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'streaming_messages',
        filter: `room_id=eq.${this.roomId},thread_id=eq.${this.threadId}`
      }, (payload) => this.handleStreamingUpdate(payload))
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'messages',
        filter: `room_id=eq.${this.roomId},thread_id=eq.${this.threadId}`
      }, (payload) => this.handleNewMessage(payload))
      .subscribe();
  }
  
  handleStreamingUpdate(payload) {
    const { eventType, new: data, old } = payload;
    
    switch (eventType) {
      case 'INSERT':
        this.streamingMessages.set(data.id, data);
        this.onStreamingStart?.(data);
        break;
        
      case 'UPDATE':
        if (data.is_complete) {
          this.streamingMessages.delete(data.id);
          this.onStreamingComplete?.(data);
        } else {
          this.streamingMessages.set(data.id, data);
          this.onStreamingUpdate?.(data);
        }
        break;
        
      case 'DELETE':
        this.streamingMessages.delete(old.id);
        break;
    }
  }
  
  handleNewMessage(payload) {
    this.messages.push(payload.new);
    this.onNewMessage?.(payload.new);
  }
  
  async sendMessage(content, aiId) {
    // Save user message
    const { data: userMessage } = await this.supabase
      .from('messages')
      .insert({
        room_id: this.roomId,
        thread_id: this.threadId,
        content: content,
        sender_type: 1
      })
      .select()
      .single();
    
    // Request AI response
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        room_id: this.roomId,
        thread_id: this.threadId,
        ai_id: aiId,
        user_message_id: userMessage.id
      })
    });
    
    return response.json();
  }
  
  disconnect() {
    this.channel?.unsubscribe();
  }
}

// Usage
const chat = new ChatClient('room-id', 'thread-id');

chat.onStreamingUpdate = (data) => {
  document.getElementById('ai-response').innerText = data.content;
};

chat.onStreamingComplete = (data) => {
  document.getElementById('typing-indicator').style.display = 'none';
};

await chat.sendMessage('Hello AI!', 'ai-id');
```

### Flutter

```dart
import 'package:supabase_flutter/supabase_flutter.dart';

class ChatService {
  final String roomId;
  final String threadId;
  late RealtimeChannel _channel;
  final _streamingMessages = <String, Map<String, dynamic>>{};
  
  ChatService({required this.roomId, required this.threadId}) {
    _subscribe();
  }
  
  void _subscribe() {
    final supabase = Supabase.instance.client;
    
    _channel = supabase.channel('room-$roomId-thread-$threadId')
      ..on(
        RealtimeListenTypes.postgresChanges,
        ChannelFilter(
          event: '*',
          schema: 'public',
          table: 'streaming_messages',
          filter: 'room_id=eq.$roomId,thread_id=eq.$threadId',
        ),
        _handleStreamingUpdate,
      )
      ..on(
        RealtimeListenTypes.postgresChanges,
        ChannelFilter(
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
          filter: 'room_id=eq.$roomId,thread_id=eq.$threadId',
        ),
        _handleNewMessage,
      )
      ..subscribe();
  }
  
  void _handleStreamingUpdate(Map<String, dynamic> payload) {
    final eventType = payload['eventType'];
    final data = payload['new'] ?? {};
    final old = payload['old'] ?? {};
    
    switch (eventType) {
      case 'INSERT':
        _streamingMessages[data['id']] = data;
        onStreamingStart?.call(data);
        break;
        
      case 'UPDATE':
        if (data['is_complete'] == true) {
          _streamingMessages.remove(data['id']);
          onStreamingComplete?.call(data);
        } else {
          _streamingMessages[data['id']] = data;
          onStreamingUpdate?.call(data);
        }
        break;
        
      case 'DELETE':
        _streamingMessages.remove(old['id']);
        break;
    }
  }
  
  Future<Map<String, dynamic>> sendMessage(String content, String aiId) async {
    final supabase = Supabase.instance.client;
    
    // Save user message
    final userMessage = await supabase
      .from('messages')
      .insert({
        'room_id': roomId,
        'thread_id': threadId,
        'content': content,
        'sender_type': 1,
      })
      .select()
      .single();
    
    // Request AI response
    final response = await http.post(
      Uri.parse('$API_URL/chat/stream'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'room_id': roomId,
        'thread_id': threadId,
        'ai_id': aiId,
        'user_message_id': userMessage['id'],
      }),
    );
    
    return jsonDecode(response.body);
  }
  
  void dispose() {
    _channel.unsubscribe();
  }
}
```

## Advanced Patterns

### Multiple AI Responses

```javascript
// Request responses from multiple AIs
async function multiAIChat(userMessageId, aiIds) {
  const responses = await Promise.all(
    aiIds.map(aiId => 
      fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: roomId,
          thread_id: threadId,
          ai_id: aiId,
          user_message_id: userMessageId
        })
      }).then(r => r.json())
    )
  );
  
  // Room subscription will handle all updates
  return responses.map(r => r.streaming_message_id);
}
```

### Error Handling

```javascript
const robustSubscription = () => {
  const maxRetries = 3;
  let retryCount = 0;
  
  const subscribe = () => {
    const channel = supabase
      .channel(`room-${roomId}`)
      .on('postgres_changes', config, handler)
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          console.log('Connected');
          retryCount = 0;
        } else if (status === 'CHANNEL_ERROR') {
          console.error('Connection failed');
          
          if (retryCount < maxRetries) {
            retryCount++;
            setTimeout(subscribe, 5000 * retryCount);
          }
        }
      });
    
    return channel;
  };
  
  return subscribe();
};
```

### Performance Optimization

```javascript
// Debounce UI updates
import { debounce } from 'lodash';

const debouncedUpdate = debounce((content) => {
  updateUI(content);
}, 100);

// In subscription handler
(payload) => {
  if (!payload.new.is_complete) {
    debouncedUpdate(payload.new.content);
  } else {
    debouncedUpdate.cancel();
    updateUI(payload.new.content);
  }
}
```

## Best Practices

1. **Always use room-level subscriptions** for multi-client sync
2. **Debounce UI updates** to prevent excessive re-renders
3. **Handle connection errors** with exponential backoff
4. **Clean up subscriptions** when components unmount
5. **Use TypeScript** for better type safety
6. **Implement loading states** during streaming
7. **Show typing indicators** for better UX

## Testing

```javascript
// Test helper
class MockSupabaseChannel {
  constructor() {
    this.handlers = new Map();
  }
  
  on(event, config, handler) {
    this.handlers.set(event, handler);
    return this;
  }
  
  subscribe(callback) {
    callback?.('SUBSCRIBED');
    return this;
  }
  
  emit(event, payload) {
    this.handlers.get(event)?.(payload);
  }
}

// Test
it('should handle streaming updates', () => {
  const channel = new MockSupabaseChannel();
  const chat = new ChatClient(channel);
  
  channel.emit('postgres_changes', {
    eventType: 'INSERT',
    new: { id: '1', content: 'Hello' }
  });
  
  expect(chat.streamingMessages.get('1')).toEqual({
    id: '1',
    content: 'Hello'
  });
});
```