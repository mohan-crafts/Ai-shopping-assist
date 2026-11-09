import { useState, useRef, useEffect } from 'react';
import { Sparkles, Send, Tag, Layers, ChevronRight, ExternalLink, Star } from 'lucide-react';

export default function App() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      headline: "Hi, I'm your AI Assist.",
      content: "Your AI shopping assistant. Ask me anything about products, compare specifications, or find recommendations tailored to your needs.",
      suggestions: [
        { label: "Show me running and athletic shoes", category: "Sports" },
        { label: "Find water shoes under $50", category: "Outdoor" },
        { label: "Top-rated football and cleats", category: "Cleats" }
      ],
      products: []
    }
  ]);
  const [inputQuery, setInputQuery] = useState('');
  const [loading, setLoading] = useState(false);
  
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSendMessage = async (textToSend) => {
    const query = textToSend || inputQuery;
    if (!query.trim() || loading) return;

    setInputQuery('');

    // Construct new user message object
    const userMessage = { role: 'user', content: query, products: [] };
    const updatedMessages = [...messages, userMessage];
    
    setMessages(updatedMessages);
    setLoading(true);

    try {
      // Send both the current query and the full message history to FastAPI
      const response = await fetch('http://localhost:8000/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          query, 
          messages: updatedMessages.map(m => ({
            role: m.role,
            content: m.content,
            products: (m.products || []).map(product => ({
              title: product.title,
              category: product.category,
              audience: product.audience,
              price: product.price,
              color: product.color || product.metadata?.color,
              size: product.size || product.metadata?.size
            })),
            filters: m.filters || []
          })),
          limit: 6 
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Search failed (${response.status}).`);
      }
      
      const assistantReply = data.assistant_message || `Here are the top recommendations matching "${query}":`;
      const productResults = data.results || [];
      
      // Handle string array or object array for dynamic suggestion chips returned by LLM
      const rawSuggestions = data.suggestions || [
        { label: "Compare top features & specs", category: "Analysis" },
        { label: "Show budget-friendly alternatives", category: "Savings" }
      ];
      
      const dynamicSuggestions = rawSuggestions.map(s => 
        typeof s === 'string' ? { label: s, category: "General" } : s
      );

      setMessages([
        ...updatedMessages,
        {
          role: 'assistant',
          headline: null,
          content: assistantReply,
          suggestions: dynamicSuggestions,
          filters: data.filters || [],
          products: productResults,
          matchType: data.match_type
        }
      ]);
    } catch (err) {
      setMessages([
        ...updatedMessages,
        {
          role: 'assistant',
          headline: null,
          content: `⚠️ Sorry, I ran into a connection issue: ${err.message}`,
          suggestions: [],
          products: []
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f3f3f3] text-[#0f1111] font-sans flex flex-col pb-32">
      <header className="bg-white border-b border-[#d5d9d9] px-6 py-3.5 flex items-center justify-between sticky top-0 z-40 shadow-xs">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-[#FF9900] to-[#ff8f00] flex items-center justify-center text-slate-950 shadow-sm">
            <Sparkles className="w-4 h-4 fill-slate-950" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-sm font-bold tracking-tight text-[#0f1111]">Shopping Assistant</h1>
            </div>
          </div>
        </div>
      </header>

      {/* Main Conversation Stream */}
      <div className="flex-1 px-4 py-8 space-y-6 max-w-3xl mx-auto w-full">
        {messages.map((msg, index) => (
          <div
            key={index}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'} space-y-4 w-full`}
          >
            {/* Assistant Turn Card */}
            {msg.role === 'assistant' ? (
              <div className="w-full bg-white border border-[#d5d9d9] rounded-2xl p-6 shadow-xs space-y-4">
                {msg.headline && (
                  <div className="flex items-center space-x-2">
                    <h2 className="text-2xl font-extrabold text-[#0f1111] tracking-tight">
                      {msg.headline}
                    </h2>
                  </div>
                )}
                <p className="text-sm text-[#0f1111] leading-relaxed font-normal">
                  {msg.content}
                </p>

                {msg.filters && msg.filters.length > 0 && (
                  <div className="flex flex-wrap gap-2" aria-label="Search filters">
                    {msg.filters.map((filter, filterIndex) => (
                      <span
                        key={`${filter.label}-${filterIndex}`}
                        className="inline-flex items-center gap-1.5 rounded-full border border-[#d5d9d9] bg-[#f8f9f9] px-3 py-1 text-[11px] text-[#565959]"
                      >
                        <span className="font-semibold text-[#0f1111]">{filter.label}:</span>
                        <span>{filter.value}</span>
                      </span>
                    ))}
                  </div>
                )}

                {/* Suggestion Cards Grid */}
                {msg.suggestions && msg.suggestions.length > 0 && (
                  <div className="pt-2 space-y-2.5">
                    <div className="text-xs font-bold text-[#565959] uppercase tracking-wider flex items-center space-x-1.5">
                      <Tag className="w-3 h-3 text-[#FF9900]" />
                      <span>Suggested explorations</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {msg.suggestions.map((suggestion, sIndex) => (
                        <button
                          key={sIndex}
                          onClick={() => handleSendMessage(suggestion.label)}
                          className="text-left bg-[#f8f9f9] hover:bg-[#f0f2f2] text-[#007185] hover:text-[#c45500] border border-[#d5d9d9] rounded-xl p-3 text-xs font-medium transition flex items-center justify-between group cursor-pointer shadow-2xs"
                        >
                          <span className="line-clamp-1">{suggestion.label}</span>
                          <ChevronRight className="w-3.5 h-3.5 text-[#565959] group-hover:translate-x-0.5 transition-transform flex-shrink-0 ml-2" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* User Bubble */
              <div className="bg-[#007185] text-white px-5 py-3 rounded-2xl rounded-br-xs text-sm max-w-lg shadow-sm font-medium">
                {msg.content}
              </div>
            )}

            {/* Product Horizontal Carousel */}
            {msg.products && msg.products.length > 0 && (
              <div className="w-full mt-2 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-bold text-[#0f1111] uppercase tracking-wider flex items-center space-x-1.5">
                    <Layers className="w-3.5 h-3.5 text-[#FF9900]" />
                    <span>
                      {msg.matchType === 'similar' ? 'Closest Matches' : 'Top Recommendations'} ({msg.products.length})
                    </span>
                  </div>
                  <span className="text-[11px] text-[#565959]">Scroll to explore →</span>
                </div>

                <div className="flex space-x-4 overflow-x-auto pb-4 pt-1">
                  {msg.products.map((product, pIndex) => {
                    const imageObj = product.metadata?.images?.find((img) => img.variant === 'MAIN') || 
                                     product.metadata?.images?.[0] || 
                                     product.images?.[0];
                    const imageUrl = imageObj?.large || imageObj?.thumb || product.image_url || 'https://via.placeholder.com/200?text=No+Image';

                    const details = product.metadata?.details || {};
                    const brandName = details['Brand Name'] || product.metadata?.store || 'Brand';
                    const color = product.color || details['Color'] || product.metadata?.color;
                    const material = details['Material'] || product.metadata?.material;
                    const rating = product.rating ?? product.metadata?.rating;

                    return (
                      <div
                        key={pIndex}
                        className="min-w-[240px] max-w-[240px] bg-white border border-[#d5d9d9] rounded-2xl overflow-hidden hover:shadow-lg transition-all duration-200 flex flex-col justify-between flex-shrink-0 group"
                      >
                        <div>
                          {/* Image Box */}
                          <div className="h-40 bg-white relative overflow-hidden flex items-center justify-center p-3 border-b border-[#f0f2f2]">
                            <img
                              src={imageUrl}
                              alt={product.title || 'Product'}
                              className="object-contain h-full w-full group-hover:scale-105 transition duration-300"
                              onError={(e) => { e.target.src = 'https://via.placeholder.com/200?text=Image+Error'; }}
                            />
                            <div className="absolute top-2 right-2 bg-slate-900/70 backdrop-blur-xs text-white text-[10px] px-2 py-0.5 rounded-full font-semibold">
                              Match #{pIndex + 1}
                            </div>
                          </div>

                          {/* Metadata & Title Info */}
                          <div className="p-3.5 space-y-1.5">
                            <div className="flex items-center justify-between text-[11px] text-[#565959]">
                              <span className="font-bold text-[#007185] uppercase tracking-wide">{brandName}</span>
                              {rating != null ? (
                                <div className="flex items-center space-x-1 text-amber-600 font-semibold">
                                  <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                                  <span>{rating}</span>
                                </div>
                              ) : (
                                <span>Not rated</span>
                              )}
                            </div>

                            <h3 className="font-medium text-xs text-[#0f1111] line-clamp-2 leading-snug">
                              {product.title || 'Unnamed Product'}
                            </h3>

                            {/* Color & Material Badges */}
                            <div className="flex flex-wrap gap-1 pt-1">
                              {color && color !== 'nan' && (
                                <span className="bg-[#f0f2f2] text-[#565959] text-[10px] px-2 py-0.5 rounded-md font-medium">
                                  {color}
                                </span>
                              )}
                              {material && material !== 'nan' && (
                                <span className="bg-[#f0f2f2] text-[#565959] text-[10px] px-2 py-0.5 rounded-md font-medium">
                                  {material}
                                </span>
                              )}
                            </div>

                            <p className="text-[#b12704] font-extrabold text-base pt-1">
                              {product.price != null ? `$${product.price}` : 'Price unavailable'}
                            </p>
                          </div>
                        </div>

                        {/* Action Footer */}
                        <div className="p-3 pt-0">
                          <button
                            onClick={() => alert(`Opening details for: ${product.title}\nStore: ${brandName}\nPrice: ${product.price != null ? `$${product.price}` : 'Unavailable'}`)}
                            className="w-full bg-[#ffd814] hover:bg-[#f7ca00] active:bg-[#f0b800] text-[#0f1111] border border-[#fcd200] text-xs font-bold py-2 rounded-xl shadow-2xs transition flex items-center justify-center space-x-1 cursor-pointer"
                          >
                            <span>View Details</span>
                            <ExternalLink className="w-3 h-3 text-[#0f1111]" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Loading Indicator */}
        {loading && (
          <div className="bg-white border border-[#d5d9d9] rounded-2xl p-4 shadow-xs flex items-center space-x-3 w-full animate-pulse">
            <div className="w-7 h-7 rounded-xl bg-[#FF9900]/20 text-[#FF9900] flex items-center justify-center text-xs font-bold">
              <Sparkles className="w-4 h-4 animate-spin text-[#FF9900]" />
            </div>
            <div className="flex flex-col">
              <span className="text-xs font-bold text-[#0f1111]">Searching the catalog</span>
              <span className="text-[11px] text-[#565959]">Checking products against your request...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Floating Interactive Input Bar */}
      <div className="bottom-0 left-0 right-0 bg-white/90 backdrop-blur-md border-t border-[#d5d9d9] p-4 z-50 shadow-2xl pointer-events-none">
        <form 
          onSubmit={(e) => { e.preventDefault(); handleSendMessage(inputQuery); }} 
          className="max-w-3xl mx-auto flex gap-2.5 pointer-events-auto bg-white border border-[#888c8c] focus-within:border-[#e77600] focus-within:ring-3 focus-within:ring-[#e77600]/20 rounded-2xl p-2 shadow-md transition"
        >
          <input
            type="text"
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            placeholder="Ask anything about products, features, or comparisons..."
            className="flex-1 bg-transparent border-none px-3 py-2 text-sm text-[#0f1111] placeholder-[#565959] focus:outline-none cursor-text pointer-events-auto font-medium"
          />
          <button
            type="submit"
            disabled={loading || !inputQuery.trim()}
            className="bg-[#ffd814] hover:bg-[#f7ca00] active:bg-[#f0b800] disabled:opacity-40 disabled:cursor-not-allowed text-[#0f1111] border border-[#fcd200] px-6 py-2.5 rounded-xl text-xs font-extrabold transition shadow-xs flex items-center space-x-1.5 justify-center cursor-pointer pointer-events-auto"
          >
            <span>Ask</span>
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>
    </div>
  );
}