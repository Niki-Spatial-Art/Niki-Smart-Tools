# Short-Term Stock Expansion Plan

This is the expansion rule for the stock satellite bucket.

It is designed to allow offensive days, not to force daily profit. The target of 3,000 yuan is only valid on strong resonance days.

## Capital Bucket

Current trading capital reference: about 473,900 yuan.

Expanded short-term stock bucket:

```text
Default single stock: 20,000
Strong A-grade single stock: 30,000
Maximum stocks: 4
Maximum stock satellite bucket: 100,000
```

Profit and loss math:

```text
100,000 x 3% = 3,000
100,000 x 5% = 5,000
100,000 x -3% = -3,000
```

This means the same structure that can make 3,000 can also lose 3,000. The system must treat both sides as real.

## Trade Grades

A-grade trial:

```text
Price above 20-day and 60-day averages
20-day average above 60-day average
Daily gain between 1.2% and 5.2%
Amount >= 500 million yuan
Same layer or sector has resonance
Not triggered daily loss soft stop
```

Action:

```text
Allowed capital: up to 30,000
Must wait for 09:40 or 10:45 confirmation
No market chasing
```

B-grade trial:

```text
Daily gain between 1.2% and 5.2%
Amount >= 500 million yuan
Trend or layer resonance is not fully confirmed
```

Action:

```text
Allowed capital: up to 20,000
Only one entry
No averaging down intraday
```

No-trade:

```text
Daily gain >= 5.2%
Daily drop <= -3.5%
Red signal
Data missing
Only one stock is strong while the layer is weak
Daily hard stop is triggered
```

## Daily Risk Gate

```text
Daily profit target: 3,000
Soft stop: -1,200
Hard stop: -2,000
Single trade stop loss: about -3%
```

Rules:

```text
If daily loss reaches -1,200, no expansion.
If daily loss reaches -2,000, no new positions.
If one trade fails, do not increase size to win it back.
If no A-grade or B-grade candidate appears, do nothing.
```

## Emotional Rule

The system is allowed to pursue proof through process, not through one forced day.

The sentence to obey:

```text
I do not need to earn 3,000 today to prove I can build the machine.
I need to follow the rules today to prove I can survive long enough for the machine to work.
```

