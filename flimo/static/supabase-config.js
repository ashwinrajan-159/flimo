/**
 * Supabase Configuration for StreamAI Chat
 */

// Prevent duplicate declarations when script loads multiple times
if (typeof window.SUPABASE_CONFIG === 'undefined') {

    window.SUPABASE_CONFIG = {
        url: 'https://zyoqnyetxnbtexruoflr.supabase.co',
        anonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp5b3FueWV0eG5idGV4cnVvZmxyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzAzNDg4OTEsImV4cCI6MjA4NTkyNDg5MX0.tSoWXQE30Yg68MC1IAvmPE3RmZL3o1WdDDCYfqDaqH4'
    };

    window.isSupabaseConfigured = function () {
        return window.SUPABASE_CONFIG.url !== 'YOUR_SUPABASE_PROJECT_URL' &&
            window.SUPABASE_CONFIG.anonKey !== 'YOUR_SUPABASE_ANON_KEY';
    };

    window.supabaseClient = null;

    window.initSupabase = function () {
        if (!window.isSupabaseConfigured()) {
            console.warn('Supabase not configured');
            return null;
        }

        if (!window.supabase) {
            console.error('Supabase client library not loaded');
            return null;
        }

        if (!window.supabaseClient) {
            window.supabaseClient = window.supabase.createClient(
                window.SUPABASE_CONFIG.url,
                window.SUPABASE_CONFIG.anonKey
            );
            console.log('Supabase client initialized');
        }

        return window.supabaseClient;
    };

    console.log('Supabase config loaded');
}
