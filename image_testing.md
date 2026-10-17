## TEST AGENT PROMPT – IMAGE INTEGRATION RULES ##
- Always use base64-encoded images for all tests and requests.
- Accepted formats: JPEG, PNG, WEBP only. No SVG/BMP/HEIC.
- Do not upload blank, solid-color, or uniform-variance images. Every image must contain real visual features (objects, edges, textures).
- If the image is animated, extract the first frame only. Re-detect MIME after transformations.
- Resize large images to reasonable bounds.
