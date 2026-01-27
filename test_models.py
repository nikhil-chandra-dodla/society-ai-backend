import google.generativeai as genai

# PASTE YOUR KEY HERE
genai.configure(api_key="AIzaSyBhbqlVDe_02SMtGyWvh-6pH6sLCr4ooFc")

print("Checking available models...")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)