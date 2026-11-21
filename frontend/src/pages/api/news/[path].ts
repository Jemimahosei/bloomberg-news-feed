import { NextApiRequest, NextApiResponse } from 'next';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
    // Forward any query string (e.g. ?symbols=AAPL) to the backend.
    const queryString = req.url?.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
    const url = `${process.env.BACKEND_API_URL}/${req.query.path}${queryString}`;

    if (req.method === 'GET') {
        // Handle GET request

        // fetch data from the backend
        const response = await fetch(url);

        res.status(200).json(await response.json());
    } else if (req.method === 'POST') {
        // Handle POST request
        res.status(200).json({ message: 'This is a POST request' });
    } else {
        // Handle other HTTP methods
        res.setHeader('Allow', ['GET', 'POST']);
        res.status(405).end(`Method ${req.method} Not Allowed`);
    }
}
