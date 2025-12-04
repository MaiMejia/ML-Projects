### Machine Learning Projects
This repository showcases ML projects I have developed across different domains.

#### 1. Classification 
A fast‑growing logistics startup was struggling to keep customers satisfied despite repeated efforts to identify improvements. To address this, I set up a machine learning model to predict whether customers were happy or unhappy with delivery services. I tested several approaches, including PCA, Random Forest, and other boosting methods, and found that AdaBoost delivered the best performance with 73% accuracy. While further data will be needed to push accuracy higher, this result provided actionable insights and measurable gains in understanding customer satisfaction, helping the company take initial steps toward improving service quality.
<br>_[View Classification Code](classification/CustomerSatisfaction.ipynb)_

#### 2. Prediction
A small startup in the European banking market was seeking to improve customer call success rates by leveraging call center data. The task was to design a machine learning system that could predict whether a customer would subscribe to a term deposit. I explored multiple approaches and developed an evolving product focused on both performance and interpretability, ultimately building an XGBoost model. This model achieved a recall of 88% for detecting positive subscriptions and showed consistent classification across features, providing strong predictive power and actionable insights to help clients make more informed decisions.
<br>_[View Prediction Code](prediction/Predicting_Subscription.ipynb)_

#### 3. NLP 
A talent sourcing company needed a way to efficiently match candidates to tech openings, but struggled with understanding roles, defining required skills, and reaching the best job seekers. I set out to automate the process by predicting candidate fit from available information. I tested several approaches and found that a TF‑DFI model with exact keyword matching produced the strongest rankings, while neural methods like CBOW and Skip‑Gram did not improve results. Filtering by score thresholds helped refine matches depending on job title frequency, and fuzzy matching was identified as a useful mitigation for vocabulary or spelling bias. The model delivered better candidate rankings and provided a scalable path to connect with top performers more effectively.
<br>_[View NLP Code](nlp/Potential_Talents.ipynb)_

#### 4. CNN 
A start‑up developing AI and computer vision solutions wanted to create MonReader, a mobile app for fast, high‑quality document digitization that could support the blind, researchers, and anyone needing bulk scanning. The challenge was to build a system that automatically detected page flips, captured high‑resolution images, corrected distortions, and preserved text formatting. I experimented with several CNNs, but initial models overfit, showing higher training accuracy than validation accuracy. By integrating augmented data and a pre‑trained model, I achieved much stronger metrics and eliminated overfitting, delivering a robust solution that improved the reliability and usability of MonReader.
<br>_[View CNN Code](cnn/ComputerVision.ipynb)_

#### 5. Systems Developer - Crypto Trading
A fintech company set out to build a smart bitcoin trading system capable of running 24/7 with minimal human supervision and adapting to volatile market conditions. My task was to design an agent that could manage budgets, switch strategies, and make autonomous trading decisions. I implemented Dollar‑Cost Averaging for accumulation, an ATR‑based stop‑loss for risk control, and integrated real‑time alerts via Telegram and weekly Gmail reports. After backtesting, the combined technical analysis and sentiment strategy performed strongly in bullish, high‑momentum markets but was less effective in range‑bound conditions. Once deployed on AWS EC2, the bot operated continuously for several weeks, successfully executing trades and delivering notifications, demonstrating practical gains in automated crypto trading.
<br>_[View Trading Bot Code](ml-tradingbot/btc_bot.py)_
