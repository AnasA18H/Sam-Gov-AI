# Frontend Assets Directory

This directory contains static assets (images, icons, etc.) for the frontend application.

## Structure

Files placed in this directory will be served at the root path `/assets/` when the application is running.

## Example

- File: `frontend/public/assets/Login.jpg`
- URL: `/assets/Login.jpg`

## Current Assets

- `Login.jpg` - Login/Signup page background image

## Adding New Assets

1. Place image files in this directory
2. Reference them in your components using `/assets/filename.ext`
3. The files will be automatically included in the build

## Notes

- Vite serves files from the `public` directory at the root path
- Use relative paths like `/assets/image.jpg` in your React components
- Images are copied as-is during the build process
